"""
SARA Crawl Worker

Pulls crawl jobs one-at-a-time from the 'sara-crawl-jobs' RabbitMQ queue
and executes crawl_runner.py for each job.

Architecture:
    Scheduler (timer) → publishes job JSON to 'sara-crawl-jobs'
    Each worker       → polls queue, runs one crawl, polls again

Why poll (basic_get) instead of subscribe (basic_consume):
    Crawls take up to 8 hours. RabbitMQ would drop a basic_consume connection
    during a long crawl due to missed heartbeats. With basic_get we connect,
    grab one job, immediately disconnect, run the crawl, then reconnect.
    No heartbeat issues, no lost ACKs.

Redis heartbeat (when REDIS_URL is set):
    Every HEARTBEAT_INTERVAL seconds, writes:
        sara:worker:{hostname}:{worker_id}:heartbeat  → Unix timestamp (TTL 90s)
        sara:worker:{hostname}:{worker_id}:info       → JSON {hostname, pid, started, version}
    When a crawl is running, also writes:
        sara:worker:{hostname}:{worker_id}:job        → JSON job details (TTL 12h)
    The dashboard scans sara:worker:*:heartbeat to show all live workers.

Start multiple workers (managed by systemd):
    systemctl start sara-worker@1 ... sara-worker@5

Or for local testing:
    WORKER_ID=1 python -m services.worker.main
    WORKER_ID=2 python -m services.worker.main   # in a second terminal
"""
from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pika
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

# ── config ─────────────────────────────────────────────────────────────────────

CLOUDAMQP_URL      = os.environ["CLOUDAMQP_URL"]
JOB_QUEUE          = "sara-crawl-jobs"
POLL_INTERVAL      = 15          # seconds between queue polls when idle
CRAWL_TIMEOUT      = int(os.environ.get("CRAWL_TIMEOUT", str(8 * 3600)))  # 8h cap
RECONNECT_DELAY    = 5           # seconds before reconnecting after RabbitMQ error
WORKER_ID          = os.environ.get("WORKER_ID", "1")
HOSTNAME           = socket.gethostname()
HEARTBEAT_INTERVAL = 30          # seconds between Redis heartbeat refreshes
HEARTBEAT_TTL      = 90          # seconds before heartbeat key auto-expires

VERSION = "2.0"

# ── logging ────────────────────────────────────────────────────────────────────

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [worker-{WORKER_ID}@{HOSTNAME}] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / f"worker-{WORKER_ID}.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(f"sara.worker.{WORKER_ID}")


# ── Redis heartbeat ────────────────────────────────────────────────────────────

def _get_redis():
    """Return a Redis client or None."""
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        return None
    try:
        import redis as _rl
        client = _rl.Redis.from_url(
            redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )
        client.ping()
        return client
    except Exception as exc:
        log.debug("Redis heartbeat unavailable: %s", exc)
        return None


_redis_client = None
_current_job: dict | None = None
_hb_stop      = threading.Event()

_HB_KEY_HB   = f"sara:worker:{HOSTNAME}:{WORKER_ID}:heartbeat"
_HB_KEY_INFO = f"sara:worker:{HOSTNAME}:{WORKER_ID}:info"
_HB_KEY_JOB  = f"sara:worker:{HOSTNAME}:{WORKER_ID}:job"


def _heartbeat_loop() -> None:
    """Background thread: refresh Redis heartbeat every HEARTBEAT_INTERVAL seconds."""
    global _redis_client
    _redis_client = _get_redis()
    if _redis_client is None:
        return

    info = json.dumps({
        "hostname":   HOSTNAME,
        "worker_id":  WORKER_ID,
        "pid":        os.getpid(),
        "started_at": datetime.utcnow().isoformat() + "Z",
        "version":    VERSION,
    })

    while not _hb_stop.is_set():
        try:
            _redis_client.setex(_HB_KEY_HB,   HEARTBEAT_TTL, str(time.time()))
            _redis_client.setex(_HB_KEY_INFO,  HEARTBEAT_TTL * 10, info)
            if _current_job:
                _redis_client.setex(_HB_KEY_JOB, 12 * 3600, json.dumps(_current_job))
        except Exception as exc:
            log.debug("Heartbeat write failed: %s", exc)
        _hb_stop.wait(timeout=HEARTBEAT_INTERVAL)

    # Worker shutting down — clean up heartbeat keys
    try:
        _redis_client.delete(_HB_KEY_HB, _HB_KEY_JOB)
    except Exception:
        pass


def _set_current_job(job: dict | None) -> None:
    global _current_job
    _current_job = job
    if _redis_client is None:
        return
    try:
        if job:
            _redis_client.setex(_HB_KEY_JOB, 12 * 3600, json.dumps(job))
        else:
            _redis_client.delete(_HB_KEY_JOB)
    except Exception:
        pass


# ── queue helpers ──────────────────────────────────────────────────────────────

def _connect() -> tuple:
    """Return (connection, channel) with the job queue declared."""
    params  = pika.URLParameters(CLOUDAMQP_URL)
    conn    = pika.BlockingConnection(params)
    channel = conn.channel()
    channel.queue_declare(
        queue=JOB_QUEUE,
        durable=True,
        arguments={"x-max-priority": 10},
    )
    return conn, channel


def _pull_job() -> dict | None:
    """
    Connect to RabbitMQ, pull one job with auto_ack, disconnect.

    auto_ack=True: the job is removed from the queue the moment we receive it.
    Acceptable because the scheduler re-dispatches at the next window if needed.
    Keeping the connection open for 8 h would break RabbitMQ heartbeats.
    """
    conn = channel = None
    try:
        conn, channel = _connect()
        method, _, body = channel.basic_get(queue=JOB_QUEUE, auto_ack=True)
        if body is None:
            return None
        return json.loads(body)
    except Exception as e:
        log.warning("RabbitMQ pull failed: %s", e)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── graceful shutdown ──────────────────────────────────────────────────────────

_current_proc: subprocess.Popen | None = None


def _handle_sigterm(signum, frame):
    log.info("Worker %s received SIGTERM — stopping", WORKER_ID)
    if _current_proc is not None and _current_proc.poll() is None:
        log.info("Terminating crawl subprocess PID %d", _current_proc.pid)
        _current_proc.terminate()
        try:
            _current_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _current_proc.kill()
    _hb_stop.set()
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)


# ── crawl execution ────────────────────────────────────────────────────────────

def _run_crawl(job: dict) -> int:
    """Run crawl_runner.py for the given job. Returns exit code."""
    global _current_proc

    project     = job["project"]
    site        = job["site"]
    schedule_id = job["schedule_id"]
    priority    = job.get("priority", 5)

    log.info(
        "Starting crawl: %s/%s  schedule_id=%s  priority=%d  timeout=%dh",
        project, site, schedule_id, priority, CRAWL_TIMEOUT // 3600,
    )

    job_record = {
        **job,
        "worker_id":  WORKER_ID,
        "hostname":   HOSTNAME,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "pid":        os.getpid(),
    }
    _set_current_job(job_record)

    cmd = [
        sys.executable,
        str(ROOT / "crawl_runner.py"),
        project, site, schedule_id,
    ]
    started = time.time()
    try:
        _current_proc = subprocess.Popen(cmd, cwd=str(ROOT))
        try:
            _current_proc.wait(timeout=CRAWL_TIMEOUT)
        except subprocess.TimeoutExpired:
            log.error(
                "Crawl TIMED OUT after %dh: %s/%s — killing",
                CRAWL_TIMEOUT // 3600, project, site,
            )
            _current_proc.kill()
            _current_proc.wait()
            return -1

        elapsed = time.time() - started
        rc = _current_proc.returncode
        if rc == 0:
            log.info("Crawl done: %s/%s  (%.0fs)", project, site, elapsed)
        else:
            log.error("Crawl FAILED: %s/%s  exit=%d  (%.0fs)", project, site, rc, elapsed)
        return rc

    except Exception:
        log.exception("Unexpected error running crawl: %s/%s", project, site)
        return -2
    finally:
        _current_proc = None
        _set_current_job(None)


# ── DLQ replay ────────────────────────────────────────────────────────────────

def _replay_dlq(limit: int = 10) -> int:
    """
    Pull up to `limit` messages from sara-dlq and re-publish them to sara-crawl-jobs.
    Returns the number of messages replayed.
    """
    replayed = 0
    conn = channel = None
    try:
        conn, channel = _connect()
        channel.queue_declare(queue="sara-dlq", durable=True)
        for _ in range(limit):
            method, _, body = channel.basic_get(queue="sara-dlq", auto_ack=False)
            if body is None:
                break
            try:
                record = json.loads(body)
                # Re-publish as a new crawl job
                job = {
                    "project":      record.get("project", ""),
                    "site":         record.get("site", ""),
                    "schedule_id":  datetime.utcnow().strftime("%Y%m%d%H%M%S"),
                    "priority":     3,   # lower priority for replays
                    "dispatched_at": datetime.utcnow().isoformat(),
                    "replayed_from_dlq": True,
                }
                channel.basic_publish(
                    exchange="",
                    routing_key=JOB_QUEUE,
                    body=json.dumps(job).encode(),
                    properties=pika.BasicProperties(delivery_mode=2, priority=3),
                )
                channel.basic_ack(delivery_tag=method.delivery_tag)
                replayed += 1
                log.info("Replayed DLQ entry: %s/%s", job["project"], job["site"])
            except Exception as exc:
                log.warning("DLQ replay error: %s", exc)
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    except Exception:
        log.exception("DLQ replay failed")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return replayed


# ── main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    log.info(
        "Worker %s starting on %s — queue='%s'  poll=%ds  timeout=%dh",
        WORKER_ID, HOSTNAME, JOB_QUEUE, POLL_INTERVAL, CRAWL_TIMEOUT // 3600,
    )

    # Start Redis heartbeat in background
    hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    hb_thread.start()

    while True:
        try:
            job = _pull_job()

            if job is None:
                time.sleep(POLL_INTERVAL)
                continue

            _run_crawl(job)

        except KeyboardInterrupt:
            log.info("Worker %s stopping (KeyboardInterrupt)", WORKER_ID)
            _hb_stop.set()
            break
        except Exception:
            log.exception("Unexpected error in worker loop — restarting in %ds", RECONNECT_DELAY)
            _set_current_job(None)
            time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    # Support: python -m services.worker.main --replay-dlq
    if "--replay-dlq" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--replay-dlq") + 1]) if len(sys.argv) > sys.argv.index("--replay-dlq") + 1 else 10
        n = _replay_dlq(limit)
        print(f"Replayed {n} DLQ entries")
        sys.exit(0)
    main()
