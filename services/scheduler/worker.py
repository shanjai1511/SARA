"""
SARA Crawl Scheduler

Reads config/schedules.json and triggers crawl_runner.py for each site
at the configured frequency. Runs as a persistent background process.

Schedule config format:
{
  "commerce_crawl": {
    "myntra_com": {
      "frequency": "daily",   # daily | weekly | hourly | custom
      "hour": 2,              # 0-23
      "minute": 0,            # 0-59
      "day_of_week": "mon",   # for weekly: mon/tue/wed/thu/fri/sat/sun
      "cron": "0 2 * * *",    # for custom frequency
      "enabled": true,
      "last_run": null,
      "next_run": null
    }
  }
}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

SCHEDULES_FILE = ROOT / "config" / "schedules.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

scheduler = BlockingScheduler(timezone="Asia/Kolkata")


def _load_schedules() -> dict:
    if not SCHEDULES_FILE.exists():
        return {}
    with open(SCHEDULES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_schedules(data: dict) -> None:
    with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _run_crawl(project: str, site: str) -> None:
    schedule_id = datetime.now().strftime("%Y%m%d%H%M%S")
    log.info("Triggering crawl: project=%s site=%s schedule_id=%s", project, site, schedule_id)

    # Update last_run in schedules.json
    data = _load_schedules()
    if project in data and site in data[project]:
        data[project][site]["last_run"] = datetime.now().isoformat()
    _save_schedules(data)

    cmd = [sys.executable, str(ROOT / "crawl_runner.py"), project, site, schedule_id]
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=7200)
        if result.returncode == 0:
            log.info("Crawl completed: project=%s site=%s", project, site)
        else:
            log.error("Crawl failed: project=%s site=%s\n%s", project, site, result.stderr[-500:])
    except subprocess.TimeoutExpired:
        log.error("Crawl timed out (2h): project=%s site=%s", project, site)
    except Exception:
        log.exception("Crawl error: project=%s site=%s", project, site)


def _make_trigger(config: dict) -> CronTrigger | None:
    freq = config.get("frequency", "daily")
    hour = config.get("hour", 2)
    minute = config.get("minute", 0)

    if freq == "hourly":
        return CronTrigger(minute=minute)
    elif freq == "daily":
        return CronTrigger(hour=hour, minute=minute)
    elif freq == "weekly":
        day = config.get("day_of_week", "mon")
        return CronTrigger(day_of_week=day, hour=hour, minute=minute)
    elif freq == "custom":
        cron = config.get("cron", "0 2 * * *")
        parts = cron.strip().split()
        if len(parts) == 5:
            return CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4],
            )
    return None


def _register_jobs() -> None:
    """Remove all jobs and re-register from schedules.json."""
    scheduler.remove_all_jobs()
    data = _load_schedules()

    for project, sites in data.items():
        for site, config in sites.items():
            if not config.get("enabled", False):
                continue
            trigger = _make_trigger(config)
            if trigger is None:
                log.warning("Invalid schedule config for %s/%s", project, site)
                continue
            job_id = f"{project}__{site}"
            scheduler.add_job(
                _run_crawl,
                trigger=trigger,
                args=[project, site],
                id=job_id,
                replace_existing=True,
                name=f"{project}/{site}",
            )
            log.info("Scheduled %s/%s (%s)", project, site, config.get("frequency", "daily"))

    # Reload jobs every 5 minutes to pick up dashboard changes
    scheduler.add_job(
        _register_jobs,
        "interval",
        minutes=5,
        id="__reload__",
        replace_existing=True,
    )


def main() -> None:
    log.info("SARA Scheduler starting — schedules file: %s", SCHEDULES_FILE)
    _register_jobs()
    log.info("Scheduler running. Jobs: %d", len(scheduler.get_jobs()) - 1)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
