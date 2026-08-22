import argparse
import sys
import time
import subprocess as _subprocess
from typing import NoReturn, Optional

from dotenv import load_dotenv #type: ignore
load_dotenv()

from sdf_module.files_import import *
from sdf_module import crawl_status
from sdf_module.crawl_context import CrawlContext
from core.alerting import send_failure_alert, send_success_alert
from core.broker import get_sync_channel as _get_sync_channel, publish_sync as _publish_sync
from config.settings import settings as _settings
import logging

logger = logging.getLogger(__name__)


# ── Unblock service ────────────────────────────────────────────────────────────

class _UnblockManager:
    """
    Ensures the sara-unblock service is running before the crawl starts.
    Reads config from env vars; auto-starts the service if the health
    endpoint is unreachable; no-ops silently if SARA_UNBLOCK_URL is unset.
    """

    _URL     = _settings.SARA_UNBLOCK_URL
    _PORT    = _settings.UNBLOCK_PORT
    _WORKERS = _settings.UNBLOCK_WORKERS
    _READY_TIMEOUT = 20   # seconds to wait for service to become healthy

    def __init__(self) -> None:
        self._proc: Optional[_subprocess.Popen] = None

    def ensure_running(self) -> None:
        if not self._URL:
            return
        if self._is_up():
            logger.info("Unblock service already running at %s", self._URL)
            return
        self._start()

    def _start(self) -> None:
        logger.info(
            "Unblock service not detected — starting automatically on port %d",
            self._PORT,
        )
        try:
            self._proc = _subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn",
                    "services.unblock.main:app",
                    "--host", "0.0.0.0",
                    "--port", str(self._PORT),
                    "--workers", str(self._WORKERS),
                ],
                stdout=_subprocess.DEVNULL,
                stderr=_subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.warning("Could not start unblock service: %s", exc)
            return

        for _ in range(self._READY_TIMEOUT):
            time.sleep(1)
            if self._is_up():
                logger.info("Unblock service ready (pid=%d)", self._proc.pid)
                return

        logger.warning(
            "Unblock service started (pid=%d) but did not pass health check "
            "within %ds — crawl will proceed without it",
            self._proc.pid, self._READY_TIMEOUT,
        )

    def _is_up(self) -> bool:
        import urllib.request as _req
        try:
            with _req.urlopen(f"{self._URL}/health", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False


# ── Pipeline ───────────────────────────────────────────────────────────────────

class CrawlPipeline:
    """
    Orchestrates the discovery → retriever → parser pipeline for one crawl job.

    Usage:
        ctx = CrawlContext(project="media_crawl", site="vogue_in", schedule_id="20260602394")
        CrawlPipeline(ctx).run()

    Each stage runs as a child subprocess. Discovery and retriever run
    concurrently; the parser runs only after both complete successfully.
    """

    _DISCOVERY_WAIT_CAP = 1800   # max seconds to wait before launching retriever
    _DLQ_QUEUE          = "sara-dlq"

    def __init__(self, ctx: CrawlContext) -> None:
        self.ctx = ctx

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        if not self._preflight():
            logger.error("Aborting crawl — RabbitMQ not available")
            sys.exit(1)

        _UnblockManager().ensure_running()
        crawl_status.set_current_run(self.ctx.project, self.ctx.site, self.ctx.schedule_id)

        self._purge_queue()

        disc_proc = self._start_stage("discovery", self.ctx.discovery_cmd)
        if not self._wait_for_queue(disc_proc):
            self._handle_empty_discovery(disc_proc)
            return

        ret_proc = self._start_stage("retriever", self.ctx.retriever_cmd)
        self._collect(disc_proc, "discovery")
        self._collect(ret_proc,  "retriever")

        rc = self._run_sync("parser", self.ctx.parser_cmd)
        if rc != 0:
            self._fail("parser", rc)

        crawl_status.complete_current_run(
            self.ctx.project, self.ctx.site, self.ctx.schedule_id, status="completed"
        )
        send_success_alert(self.ctx.project, self.ctx.site, self.ctx.schedule_id)
        logger.info("[%s] Pipeline completed successfully", self.ctx)

    # ── Pre-flight ────────────────────────────────────────────────────────────

    @staticmethod
    def _open_channel():
        """Open a RabbitMQ connection+channel with retry, via the shared broker helper."""
        return _get_sync_channel(CLOUDAMQP_URL)

    def _preflight(self) -> bool:
        """Verify RabbitMQ is reachable before starting any work."""
        try:
            conn, _ch = self._open_channel()
            conn.close()
            logger.info("Pre-flight: RabbitMQ connection OK")
            return True
        except Exception as exc:
            logger.error("Pre-flight FAILED: RabbitMQ unreachable — %s", exc)
            return False

    # ── Queue management ──────────────────────────────────────────────────────

    def _purge_queue(self) -> None:
        """Remove stale messages left by a previous run of the same job."""
        try:
            conn, ch = self._open_channel()
            ch.queue_declare(queue=self.ctx.queue_name, durable=True)
            purged = ch.queue_purge(queue=self.ctx.queue_name)
            conn.close()
            if purged.method.message_count:
                logger.info(
                    "[%s] Purged %d stale messages from queue",
                    self.ctx, purged.method.message_count,
                )
        except Exception as exc:
            logger.warning("[%s] Queue purge failed (non-fatal): %s", self.ctx, exc)

    def _queue_depth(self) -> int:
        """Return the current message count of this job's RabbitMQ queue."""
        try:
            conn, ch = self._open_channel()
            q    = ch.queue_declare(queue=self.ctx.queue_name, durable=True, passive=True)
            count = q.method.message_count
            conn.close()
            return count
        except Exception:
            return 0

    # ── Stage lifecycle ───────────────────────────────────────────────────────

    def _start_stage(self, stage: str, cmd: list) -> _subprocess.Popen:
        """Update status and launch a stage subprocess in the background."""
        crawl_status.update_progress(
            self.ctx.project, self.ctx.site, self.ctx.schedule_id, stage=stage
        )
        logger.info("[%s] Starting %s (background)", self.ctx, stage)
        return _subprocess.Popen(
            cmd, stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, text=True
        )

    def _wait_for_queue(self, disc_proc: _subprocess.Popen) -> bool:
        """
        Poll the queue every 5 s until it has URLs or discovery exits.

        Returns True  → retriever should be launched.
        Returns False → discovery finished with 0 URLs; skip retriever + parser.
        """
        conn = ch = None
        try:
            conn, ch = self._open_channel()
        except Exception as exc:
            logger.warning(
                "[%s] Could not open polling connection (%s) — polling per-check instead",
                self.ctx, exc,
            )

        def _depth() -> int:
            if ch is not None:
                try:
                    q = ch.queue_declare(queue=self.ctx.queue_name, durable=True, passive=True)
                    return q.method.message_count
                except Exception:
                    pass
            return self._queue_depth()

        try:
            waited = 0
            while waited < self._DISCOVERY_WAIT_CAP:
                if disc_proc.poll() is not None:
                    logger.info(
                        "[%s] Discovery exited (rc=%d) after %ds",
                        self.ctx, disc_proc.returncode, waited,
                    )
                    return _depth() > 0

                count = _depth()
                if count > 0 and waited >= 60:
                    logger.info(
                        "[%s] Queue has %d URLs after %ds — launching retriever",
                        self.ctx, count, waited,
                    )
                    return True

                time.sleep(5)
                waited += 5

            logger.warning(
                "[%s] Discovery wait cap (%ds) reached — launching retriever anyway",
                self.ctx, self._DISCOVERY_WAIT_CAP,
            )
            return True
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _log_output(stage: str, stdout: str, stderr: str) -> None:
        for line in (stdout or "").splitlines():
            if line.strip():
                logger.info("[%s] %s", stage, line)
        for line in (stderr or "").splitlines():
            if line.strip():
                logger.error("[%s] %s", stage, line)

    def _collect(self, proc: _subprocess.Popen, stage: str) -> None:
        """
        Wait for a background stage to finish, log its output, and fail-fast
        if the exit code is non-zero.
        """
        stdout, stderr = proc.communicate()
        self._log_output(stage, stdout, stderr)
        if proc.returncode != 0:
            logger.error("[%s] %s failed (exit %d)", self.ctx, stage, proc.returncode)
            self._fail(stage, proc.returncode, stderr or "")

    def _run_sync(self, stage: str, cmd: list) -> int:
        """Run a stage synchronously, stream its output to the log, return exit code."""
        crawl_status.update_progress(
            self.ctx.project, self.ctx.site, self.ctx.schedule_id, stage=stage
        )
        result = _subprocess.run(cmd, capture_output=True, text=True)
        self._log_output(stage, result.stdout, result.stderr)
        if result.returncode != 0:
            logger.error("[%s] %s failed (exit %d)", self.ctx, stage, result.returncode)
        else:
            logger.info("[%s] %s completed", self.ctx, stage)
        return result.returncode

    def _handle_empty_discovery(self, disc_proc: _subprocess.Popen) -> None:
        """Discovery produced 0 URLs — log, alert if it crashed, then mark done."""
        self._collect(disc_proc, "discovery")

        logger.warning("[%s] Discovery produced 0 URLs — skipping retriever and parser", self.ctx)
        crawl_status.complete_current_run(
            self.ctx.project, self.ctx.site, self.ctx.schedule_id, status="completed"
        )
        send_success_alert(self.ctx.project, self.ctx.site, self.ctx.schedule_id)

    # ── Error handling ────────────────────────────────────────────────────────

    def _fail(self, stage: str, returncode: int, stderr: str = "") -> NoReturn:
        """Mark the run failed, send alerts, publish to DLQ, and exit."""
        crawl_status.complete_current_run(
            self.ctx.project, self.ctx.site, self.ctx.schedule_id, status="failed"
        )
        send_failure_alert(
            self.ctx.project, self.ctx.site, self.ctx.schedule_id,
            stage=stage, error_detail=stderr[-1000:],
        )
        self._publish_dlq(stage, stderr[-500:])
        sys.exit(returncode)

    def _publish_dlq(self, stage: str, error: str = "") -> None:
        """Push a failure record to the dead-letter queue for later inspection."""
        payload = {
            "project":     self.ctx.project,
            "site":        self.ctx.site,
            "schedule_id": self.ctx.schedule_id,
            "stage":       stage,
            "error":       error,
            "failed_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            conn, ch = self._open_channel()
            ch.queue_declare(queue=self._DLQ_QUEUE, durable=True)
            _publish_sync(ch, exchange="", routing_key=self._DLQ_QUEUE, body=payload)
            conn.close()
            logger.info(
                "Published failure record to %s for %s stage=%s",
                self._DLQ_QUEUE, self.ctx, stage,
            )
        except Exception as exc:
            logger.warning("Could not publish to %s: %s", self._DLQ_QUEUE, exc)


# ── CLI entry point ────────────────────────────────────────────────────────────

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Run discovery → retriever → parser pipeline for a project/site schedule."
    )
    parser.add_argument("project",     help="Project name")
    parser.add_argument("site",        help="Site name")
    parser.add_argument("schedule_id", help="Schedule ID")
    args = parser.parse_args(argv)

    ctx = CrawlContext(
        project=args.project,
        site=args.site,
        schedule_id=args.schedule_id,
    )
    CrawlPipeline(ctx).run()


if __name__ == "__main__":
    main()
