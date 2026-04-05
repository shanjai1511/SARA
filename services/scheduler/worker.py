"""
SARA Crawl Scheduler

Reads config/schedules.json and triggers crawl_runner.py for each site
at the configured frequency.

Fix 2: replaced BlockingScheduler (single-threaded, serialises all crawls)
with BackgroundScheduler + ThreadPoolExecutor so multiple sites run
concurrently without blocking each other.

Schedule config format:
{
  "commerce_crawl": {
    "myntra_com": {
      "frequency": "daily",   # daily | weekly | hourly | custom
      "hour": 2,              # 0-23
      "minute": 0,            # 0-59
      "day_of_week": "mon",   # for weekly
      "cron": "0 2 * * *",    # for custom
      "enabled": true,
      "last_run": null
    }
  }
}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from apscheduler.executors.pool import ThreadPoolExecutor as APThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

SCHEDULES_FILE = ROOT / "config" / "schedules.json"

# Max crawls that can run simultaneously. Each crawl runs in its own thread,
# blocking on a subprocess. 10 is safe for a 4-core machine.
MAX_CONCURRENT_CRAWLS = 10

# Per-crawl timeout in seconds. 8 hours covers large sites (5 000+ URLs).
CRAWL_TIMEOUT_SEC = 8 * 3600

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# Fix 2: BackgroundScheduler with a thread pool — jobs run concurrently
scheduler = BackgroundScheduler(
    executors={"default": APThreadPoolExecutor(max_workers=MAX_CONCURRENT_CRAWLS)},
    timezone="Asia/Kolkata",
    job_defaults={
        "coalesce": True,       # skip missed runs instead of catching up
        "max_instances": 1,     # one instance of each site at a time
        "misfire_grace_time": 300,  # allow 5-minute late start
    },
)


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


def _run_crawl(project: str, site: str) -> None:
    """
    Execute one crawl in the calling thread (which is a pool thread).
    Multiple sites therefore run in parallel automatically.
    """
    schedule_id = datetime.now().strftime("%Y%m%d%H%M%S")
    log.info("Triggering crawl: %s/%s  schedule_id=%s", project, site, schedule_id)

    # Record last_run immediately so the dashboard shows it
    try:
        data = _load_schedules()
        if project in data and site in data[project]:
            data[project][site]["last_run"] = datetime.now().isoformat()
        _save_schedules(data)
    except Exception:
        log.warning("Could not update last_run for %s/%s", project, site)

    cmd = [sys.executable, str(ROOT / "crawl_runner.py"), project, site, schedule_id]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=CRAWL_TIMEOUT_SEC,
        )
        if result.returncode == 0:
            log.info("Crawl completed: %s/%s", project, site)
        else:
            log.error(
                "Crawl FAILED: %s/%s (exit %d)\n%s",
                project, site, result.returncode, result.stderr[-1000:],
            )
    except subprocess.TimeoutExpired:
        log.error(
            "Crawl timed out after %dh: %s/%s",
            CRAWL_TIMEOUT_SEC // 3600, project, site,
        )
    except Exception:
        log.exception("Crawl error: %s/%s", project, site)


def _make_trigger(config: dict) -> CronTrigger | None:
    freq   = config.get("frequency", "daily")
    hour   = config.get("hour", 2)
    minute = config.get("minute", 0)

    if freq == "hourly":
        return CronTrigger(minute=minute)
    if freq == "daily":
        return CronTrigger(hour=hour, minute=minute)
    if freq == "weekly":
        return CronTrigger(day_of_week=config.get("day_of_week", "mon"),
                           hour=hour, minute=minute)
    if freq == "custom":
        parts = config.get("cron", "0 2 * * *").strip().split()
        if len(parts) == 5:
            return CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4],
            )
    return None


def _register_jobs() -> None:
    """Remove all site jobs and re-register from schedules.json.
    The __reload__ job that calls this function is preserved.
    """
    # Remove site jobs only (keep __reload__ intact)
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
                log.warning("Invalid schedule config for %s/%s — skipping", project, site)
                continue
            scheduler.add_job(
                _run_crawl,
                trigger=trigger,
                args=[project, site],
                id=f"{project}__{site}",
                replace_existing=True,
                name=f"{project}/{site}",
            )
            log.info("Scheduled %s/%s  (%s)", project, site, config.get("frequency", "daily"))
            registered += 1

    log.info("Jobs registered: %d", registered)


def main() -> None:
    log.info("SARA Scheduler starting — schedules: %s", SCHEDULES_FILE)

    # Register jobs before starting the scheduler
    _register_jobs()

    # Reload every 5 minutes so dashboard changes are picked up
    scheduler.add_job(
        _register_jobs,
        "interval",
        minutes=5,
        id="__reload__",
        replace_existing=True,
    )

    scheduler.start()
    log.info(
        "Scheduler running (max %d concurrent crawls). Press Ctrl+C to stop.",
        MAX_CONCURRENT_CRAWLS,
    )

    # Fix 2: BackgroundScheduler runs its threads as daemons; keep the main
    # thread alive with a lightweight loop so the process doesn't exit.
    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler shutting down…")
        scheduler.shutdown(wait=True)
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
