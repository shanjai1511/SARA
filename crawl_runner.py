import argparse
import re
import time
import subprocess as _subprocess
from sdf_module.files_import import *
from sdf_module import crawl_status
import logging

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_name(value: str, label: str) -> None:
    if not value or not _SAFE_NAME.match(value):
        raise ValueError(
            f"Invalid {label} '{value}': only letters, digits, underscores, "
            "and hyphens are allowed."
        )


def _preflight_check() -> bool:
    """Verify RabbitMQ is reachable before starting the pipeline."""
    try:
        conn = pika.BlockingConnection(pika.URLParameters(CLOUDAMQP_URL))
        conn.close()
        logger.info("Pre-flight: RabbitMQ connection OK")
        return True
    except Exception as e:
        logger.error("Pre-flight FAILED: RabbitMQ unreachable — %s", e)
        return False


def _run_stage(cmd: list, stage: str, schedule_id: str) -> int:
    """Run a pipeline stage subprocess, capturing and logging all output."""
    logger.info("[schedule_id=%s] Starting stage: %s", schedule_id, stage)
    result = _subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            logger.info("[%s] %s", stage, line)
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            logger.error("[%s] %s", stage, line)
    if result.returncode != 0:
        logger.error("[schedule_id=%s] Failed stage: %s (exit %d)", schedule_id, stage, result.returncode)
    else:
        logger.info("[schedule_id=%s] Completed stage: %s", schedule_id, stage)
    return result.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run discovery → retriever → parser pipeline for a project/site schedule."
    )
    parser.add_argument("project", help="Project name")
    parser.add_argument("site", help="Site name")
    parser.add_argument("schedule_id", help="Schedule ID")
    args = parser.parse_args(argv)

    project = args.project
    site = args.site
    schedule_id = args.schedule_id

    _validate_name(project, "project")
    _validate_name(site, "site")
    _validate_name(schedule_id, "schedule_id")

    # ── Fix 5: Pre-flight health check ───────────────────────────────────────
    if not _preflight_check():
        logger.error("Aborting crawl — RabbitMQ not available")
        sys.exit(1)

    crawl_status.set_current_run(project, site, schedule_id)

    disc_cmd   = [sys.executable, "-m", "sdf_module.url_discovery", project, site, schedule_id]
    ret_cmd    = [sys.executable, "-m", "sdf_module.url_retriever", project, site, schedule_id]
    parser_cmd = [sys.executable, "-m", "sdf_module.url_parser",    project, site, schedule_id]

    # ── Fix 6: Pipeline discovery + retriever concurrently ───────────────────
    # Start discovery in background
    crawl_status.update_progress(project, site, schedule_id, stage="discovery")
    logger.info("[schedule_id=%s] Starting discovery (background)", schedule_id)
    disc_proc = _subprocess.Popen(
        disc_cmd,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, text=True
    )

    # Poll RabbitMQ until discovery pushes first URLs (max 60s wait)
    queue_name = f"{site}_{project}_{schedule_id}_queue"
    waited = 0
    while waited < 60:
        try:
            conn = pika.BlockingConnection(pika.URLParameters(CLOUDAMQP_URL))
            ch = conn.channel()
            ch.queue_declare(queue=queue_name, durable=True, passive=True)
            q = ch.queue_declare(queue=queue_name, durable=True, passive=True)
            count = q.method.message_count
            conn.close()
            if count > 0:
                logger.info("[schedule_id=%s] Queue has %d URLs — starting retriever", schedule_id, count)
                break
        except Exception:
            pass
        time.sleep(5)
        waited += 5

    # Start retriever concurrently with remaining discovery
    crawl_status.update_progress(project, site, schedule_id, stage="retriever")
    ret_proc = _subprocess.Popen(
        ret_cmd,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, text=True
    )

    # Wait for both to complete and log output
    disc_stdout, disc_stderr = disc_proc.communicate()
    ret_stdout, ret_stderr = ret_proc.communicate()

    for line in (disc_stdout or "").splitlines():
        if line.strip(): logger.info("[discovery] %s", line)
    for line in (disc_stderr or "").splitlines():
        if line.strip(): logger.error("[discovery] %s", line)
    for line in (ret_stdout or "").splitlines():
        if line.strip(): logger.info("[retriever] %s", line)
    for line in (ret_stderr or "").splitlines():
        if line.strip(): logger.error("[retriever] %s", line)

    if disc_proc.returncode != 0:
        logger.error("[schedule_id=%s] Discovery failed (exit %d)", schedule_id, disc_proc.returncode)
        crawl_status.complete_current_run(project, site, schedule_id, status="failed")
        sys.exit(disc_proc.returncode)

    if ret_proc.returncode != 0:
        logger.error("[schedule_id=%s] Retriever failed (exit %d)", schedule_id, ret_proc.returncode)
        crawl_status.complete_current_run(project, site, schedule_id, status="failed")
        sys.exit(ret_proc.returncode)

    # ── Parser runs after both complete ──────────────────────────────────────
    crawl_status.update_progress(project, site, schedule_id, stage="parser")
    rc = _run_stage(parser_cmd, "parser", schedule_id)
    if rc != 0:
        crawl_status.complete_current_run(project, site, schedule_id, status="failed")
        sys.exit(rc)

    crawl_status.complete_current_run(project, site, schedule_id, status="completed")
    print(f"[schedule_id={schedule_id}] Pipeline completed successfully")


if __name__ == "__main__":
    main()
