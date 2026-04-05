import argparse
import re
from sdf_module.files_import import *
from sdf_module import crawl_status
import logging

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_name(value: str, label: str) -> None:
    """Raise ValueError if value contains characters outside [a-zA-Z0-9_-].

    Prevents path traversal attacks when user-supplied values are used to
    build file paths and RabbitMQ queue names.
    """
    if not value or not _SAFE_NAME.match(value):
        raise ValueError(
            f"Invalid {label} '{value}': only letters, digits, underscores, "
            "and hyphens are allowed."
        )


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

    crawl_status.set_current_run(project, site, schedule_id)

    commands = [
        [sys.executable, "-m", "sdf_module.url_discovery", project, site, schedule_id],
        [sys.executable, "-m", "sdf_module.url_retriever", project, site, schedule_id],
        [sys.executable, "-m", "sdf_module.url_parser", project, site, schedule_id],
    ]

    stage_names = ["discovery", "retriever", "parser"]
    for stage, cmd in zip(stage_names, commands):
        logger.info("[schedule_id=%s] Starting stage: %s", schedule_id, stage)
        crawl_status.update_progress(project, site, schedule_id, stage=stage)
        logger.debug("Running command: %s", cmd)
        result = subprocess.run(cmd)

        if result.returncode != 0:
            logger.error("[schedule_id=%s] Failed stage: %s", schedule_id, stage)
            crawl_status.complete_current_run(status="failed")
            sys.exit(result.returncode)
        logger.info("[schedule_id=%s] Completed stage: %s", schedule_id, stage)

    crawl_status.complete_current_run(status="completed")
    print(f"[schedule_id={scheduler_id}] Pipeline completed successfully")


if __name__ == "__main__":
    main()
