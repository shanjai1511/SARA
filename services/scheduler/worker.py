"""
SARA Crawl Scheduler — job dispatcher

Reads config/schedules.json and publishes crawl jobs to the
'sara-crawl-jobs' RabbitMQ queue at the configured times.

The scheduler does NOT run crawls itself. It only publishes job messages.
Actual crawling is done by sara-worker@1 … sara-worker@N processes that
consume from the same queue (see services/worker/main.py).

This separation means:
  - Scheduler is lightweight (dispatches in <1s, never blocks)
  - Workers scale independently (add more by starting more processes)
  - Scheduler restarts don't interrupt running crawls

Schedule config format (config/schedules.json):
{
  "commerce_crawl": {
    "myntra_com": {
      "frequency": "daily",
      "hour": 2,
      "minute": 0,
      "enabled": true,
      "priority": 8         # optional, 1-10 (10 = highest)
    }
  }
}

Redis tracking (when REDIS_URL is set):
  sara:scheduler:dispatch:{project}__{site}  → JSON of last dispatch (TTL 48h)
  sara:scheduler:last_dispatched             → sorted-set of recent dispatches

Manual dispatch (bypasses schedule):
    python -m services.scheduler.worker --dispatch-now commerce_crawl myntra_com
    python -m services.scheduler.worker --dispatch-now media_crawl wwd_com --priority 9
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pika
from apscheduler.executors.pool import ThreadPoolExecutor as APThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

SCHEDULES_FILE   = ROOT / "config" / "schedules.json"
CLOUDAMQP_URL    = os.environ["CLOUDAMQP_URL"]
JOB_QUEUE        = "sara-crawl-jobs"
DEFAULT_PRIORITY = 5   # RabbitMQ message priority (1-10)

_LOG_DIR = ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_DIR / "scheduler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("sara.scheduler")

# Scheduler only dispatches (instant), so a small thread pool is enough
scheduler = BackgroundScheduler(
    executors={"default": APThreadPoolExecutor(max_workers=4)},
    timezone="UTC",
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    },
)


# ── Redis (optional) ───────────────────────────────────────────────────────────

_redis = None
_redis_ok = False


def _get_redis():
    global _redis, _redis_ok
    if _redis_ok:
        return _redis
    _redis_ok = True
    try:
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if not redis_url:
            return None
        import redis as _rl
        client = _rl.Redis.from_url(
            redis_url, decode_responses=True,
            socket_timeout=2, socket_connect_timeout=2,
        )
        client.ping()
        _redis = client
        log.info("Scheduler: Redis backend connected")
    except Exception as exc:
        log.debug("Scheduler: Redis unavailable (%s) — dispatch tracking disabled", exc)
    return _redis


def _record_dispatch(project: str, site: str, schedule_id: str, priority: int) -> None:
    """Write last-dispatch metadata to Redis for dashboard visibility."""
    r = _get_redis()
    if r is None:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({
            "project":     project,
            "site":        site,
            "schedule_id": schedule_id,
            "priority":    priority,
            "dispatched_at": now,
        })
        key = f"sara:scheduler:dispatch:{project}__{site}"
        r.setex(key, 48 * 3600, payload)    # TTL: 48h
        # Sorted set of recent dispatches (score = Unix timestamp)
        r.zadd(
            "sara:scheduler:last_dispatched",
            {f"{project}__{site}__{schedule_id}": time.time()},
        )
        # Cap sorted set to last 200 entries
        r.zremrangebyrank("sara:scheduler:last_dispatched", 0, -201)
    except Exception as exc:
        log.debug("Redis dispatch record failed: %s", exc)


# ── schedule file helpers ──────────────────────────────────────────────────────

def _load_schedules() -> dict:
    if not SCHEDULES_FILE.exists():
        return {}
    try:
        with open(SCHEDULES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        log.exception("Failed to load schedules.json")
        return {}


def _save_schedules(data: dict) -> None:
    tmp = SCHEDULES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(SCHEDULES_FILE)


# ── job dispatch ───────────────────────────────────────────────────────────────

def _publish_job(project: str, site: str, priority: int = DEFAULT_PRIORITY) -> str | None:
    """
    Publish one crawl job to the RabbitMQ job queue.
    Returns schedule_id on success, None on failure.
    """
    schedule_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    job = {
        "project":       project,
        "site":          site,
        "schedule_id":   schedule_id,
        "priority":      priority,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_by": "scheduler",
    }

    conn = channel = None
    try:
        params  = pika.URLParameters(CLOUDAMQP_URL)
        conn    = pika.BlockingConnection(params)
        channel = conn.channel()
        channel.queue_declare(
            queue=JOB_QUEUE,
            durable=True,
            arguments={"x-max-priority": 10},
        )
        channel.basic_publish(
            exchange="",
            routing_key=JOB_QUEUE,
            body=json.dumps(job).encode(),
            properties=pika.BasicProperties(
                delivery_mode=2,        # persistent — survives RabbitMQ restart
                priority=priority,
            ),
        )
        log.info(
            "Dispatched: %s/%s  schedule_id=%s  priority=%d",
            project, site, schedule_id, priority,
        )

        # Update last_run in schedules.json
        data = _load_schedules()
        if project in data and site in data[project]:
            data[project][site]["last_run"] = datetime.now(timezone.utc).isoformat()
            _save_schedules(data)

        # Record in Redis for cross-server visibility
        _record_dispatch(project, site, schedule_id, priority)

        return schedule_id

    except Exception:
        log.exception("Failed to dispatch job: %s/%s", project, site)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _dispatch_job(project: str, site: str, priority: int = DEFAULT_PRIORITY) -> None:
    """Called by APScheduler at the configured time."""
    log.info("Scheduling: %s/%s  priority=%d", project, site, priority)
    _publish_job(project, site, priority)


# ── job registration ───────────────────────────────────────────────────────────

def _make_trigger(config: dict) -> CronTrigger | None:
    freq   = config.get("frequency", "daily")
    hour   = config.get("hour", 2)
    minute = config.get("minute", 0)

    if freq == "hourly":
        return CronTrigger(minute=minute)
    if freq == "daily":
        return CronTrigger(hour=hour, minute=minute)
    if freq == "weekly":
        return CronTrigger(
            day_of_week=config.get("day_of_week", "mon"),
            hour=hour, minute=minute,
        )
    if freq == "custom":
        parts = config.get("cron", "0 2 * * *").strip().split()
        if len(parts) == 5:
            return CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4],
            )
    return None


def _register_jobs() -> None:
    """Re-read schedules.json and sync APScheduler jobs."""
    for job in scheduler.get_jobs():
        if job.id != "__reload__":
            job.remove()

    data = _load_schedules()
    registered = 0

    for project, sites in data.items():
        for site, config in sites.items():
            if not config.get("enabled", False):
                continue
            trigger = _make_trigger(config)
            if trigger is None:
                log.warning("Invalid schedule for %s/%s — skipping", project, site)
                continue
            priority = int(config.get("priority", DEFAULT_PRIORITY))
            scheduler.add_job(
                _dispatch_job,
                trigger=trigger,
                args=[project, site, priority],
                id=f"{project}__{site}",
                replace_existing=True,
                name=f"{project}/{site}",
            )
            log.info(
                "Scheduled %s/%s  (%s @ %02d:%02d UTC, priority=%d)",
                project, site, config.get("frequency"),
                config.get("hour", 0), config.get("minute", 0), priority,
            )
            registered += 1

    log.info("Jobs registered: %d", registered)


# ── entry point ────────────────────────────────────────────────────────────────

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="SARA Scheduler — publish crawl jobs to RabbitMQ on a schedule."
    )
    parser.add_argument(
        "--dispatch-now", nargs=2, metavar=("PROJECT", "SITE"),
        help="Immediately dispatch a one-shot job and exit.",
    )
    parser.add_argument(
        "--priority", type=int, default=DEFAULT_PRIORITY,
        help="Priority for --dispatch-now (1-10, default: 5).",
    )
    args = parser.parse_args(argv)

    if args.dispatch_now:
        project, site = args.dispatch_now
        log.info("Manual dispatch: %s/%s  priority=%d", project, site, args.priority)
        sid = _publish_job(project, site, args.priority)
        if sid:
            print(f"Dispatched schedule_id={sid}")
            sys.exit(0)
        else:
            print("ERROR: dispatch failed", file=sys.stderr)
            sys.exit(1)

    # ── Normal long-running scheduler mode ────────────────────────────────────
    log.info("SARA Scheduler starting — dispatching to queue '%s'", JOB_QUEUE)

    _register_jobs()

    # Reload every 5 minutes to pick up dashboard schedule changes
    scheduler.add_job(
        _register_jobs,
        "interval",
        minutes=5,
        id="__reload__",
        replace_existing=True,
    )

    scheduler.start()
    log.info("Scheduler running. Jobs: %d", len(scheduler.get_jobs()) - 1)

    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler shutting down…")
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
