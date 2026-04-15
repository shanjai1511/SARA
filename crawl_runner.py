import argparse
import re
import time
import subprocess as _subprocess
from sdf_module.files_import import *
from sdf_module import crawl_status
from core.alerting import send_failure_alert, send_success_alert
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


def _publish_dlq(
    project: str, site: str, schedule_id: str, stage: str, error: str = ""
) -> None:
    """Publish a failed job record to the sara-dlq queue for later inspection."""
    import json as _json
    payload = _json.dumps({
        "project": project,
        "site": site,
        "schedule_id": schedule_id,
        "stage": stage,
        "error": error,
        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    try:
        conn = pika.BlockingConnection(pika.URLParameters(CLOUDAMQP_URL))
        ch = conn.channel()
        ch.queue_declare(queue="sara-dlq", durable=True)
        ch.basic_publish(
            exchange="",
            routing_key="sara-dlq",
            body=payload.encode(),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        conn.close()
        logger.info("Published failure record to sara-dlq for schedule_id=%s stage=%s", schedule_id, stage)
    except Exception as exc:
        logger.warning("Could not publish to sara-dlq: %s", exc)


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

    # ── Discovery + retriever concurrently ───────────────────────────────────
    # Start discovery in background
    crawl_status.update_progress(project, site, schedule_id, stage="discovery")
    logger.info("[schedule_id=%s] Starting discovery (background)", schedule_id)
    disc_proc = _subprocess.Popen(
        disc_cmd,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE, text=True
    )

    # Adaptive wait: poll queue every 5s, but stop early if:
    #   a) queue has URLs (launch retriever immediately), OR
    #   b) discovery process has exited (no point waiting further)
    # Max wait cap: 300s (5 min) to handle slow sites.
    queue_name = f"{site}_{project}_{schedule_id}_queue"
    _DISCOVERY_WAIT_CAP = 300
    waited = 0
    queue_has_urls = False
    while waited < _DISCOVERY_WAIT_CAP:
        # Check if discovery already finished
        disc_poll = disc_proc.poll()
        if disc_poll is not None:
            logger.info(
                "[schedule_id=%s] Discovery process exited (rc=%d) after %ds",
                schedule_id, disc_poll, waited,
            )
            # Do one final queue check after process exits
            try:
                conn = pika.BlockingConnection(pika.URLParameters(CLOUDAMQP_URL))
                ch = conn.channel()
                q = ch.queue_declare(queue=queue_name, durable=True, passive=True)
                queue_has_urls = q.method.message_count > 0
                conn.close()
            except Exception:
                pass
            break

        try:
            conn = pika.BlockingConnection(pika.URLParameters(CLOUDAMQP_URL))
            ch = conn.channel()
            q = ch.queue_declare(queue=queue_name, durable=True, passive=True)
            count = q.method.message_count
            conn.close()
            if count > 0:
                logger.info(
                    "[schedule_id=%s] Queue has %d URLs after %ds — starting retriever",
                    schedule_id, count, waited,
                )
                queue_has_urls = True
                break
        except Exception:
            pass
        time.sleep(5)
        waited += 5

    if waited >= _DISCOVERY_WAIT_CAP:
        logger.warning(
            "[schedule_id=%s] Discovery wait cap (%ds) reached — launching retriever anyway",
            schedule_id, _DISCOVERY_WAIT_CAP,
        )
        queue_has_urls = True  # let retriever drain whatever is there

    if not queue_has_urls:
        # Discovery finished but produced no URLs — skip retriever & parser
        disc_stdout, disc_stderr = disc_proc.communicate()
        for line in (disc_stdout or "").splitlines():
            if line.strip(): logger.info("[discovery] %s", line)
        for line in (disc_stderr or "").splitlines():
            if line.strip(): logger.error("[discovery] %s", line)
        if disc_proc.returncode != 0:
            logger.error("[schedule_id=%s] Discovery failed (exit %d)", schedule_id, disc_proc.returncode)
            crawl_status.complete_current_run(project, site, schedule_id, status="failed")
            send_failure_alert(project, site, schedule_id, stage="discovery",
                               error_detail=(disc_stderr or "")[-1000:])
            _publish_dlq(project, site, schedule_id, stage="discovery",
                         error=(disc_stderr or "")[-500:])
            sys.exit(disc_proc.returncode)
        logger.warning(
            "[schedule_id=%s] Discovery produced 0 URLs — skipping retriever and parser",
            schedule_id,
        )
        crawl_status.complete_current_run(project, site, schedule_id, status="completed")
        send_success_alert(project, site, schedule_id)
        return

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
        send_failure_alert(project, site, schedule_id, stage="discovery",
                           error_detail=(disc_stderr or "")[-1000:])
        _publish_dlq(project, site, schedule_id, stage="discovery",
                     error=(disc_stderr or "")[-500:])
        sys.exit(disc_proc.returncode)

    if ret_proc.returncode != 0:
        logger.error("[schedule_id=%s] Retriever failed (exit %d)", schedule_id, ret_proc.returncode)
        crawl_status.complete_current_run(project, site, schedule_id, status="failed")
        send_failure_alert(project, site, schedule_id, stage="retriever",
                           error_detail=(ret_stderr or "")[-1000:])
        _publish_dlq(project, site, schedule_id, stage="retriever",
                     error=(ret_stderr or "")[-500:])
        sys.exit(ret_proc.returncode)

    # ── Parser runs after both complete ──────────────────────────────────────
    crawl_status.update_progress(project, site, schedule_id, stage="parser")
    rc = _run_stage(parser_cmd, "parser", schedule_id)
    if rc != 0:
        crawl_status.complete_current_run(project, site, schedule_id, status="failed")
        send_failure_alert(project, site, schedule_id, stage="parser")
        _publish_dlq(project, site, schedule_id, stage="parser")
        sys.exit(rc)

    crawl_status.complete_current_run(project, site, schedule_id, status="completed")
    send_success_alert(project, site, schedule_id)
    logger.info("[schedule_id=%s] Pipeline completed successfully", schedule_id)


if __name__ == "__main__":
    main()
