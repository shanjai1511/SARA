from sdf_module.files_import import *
from sdf_module import crawl_status
import logging

logger = logging.getLogger(__name__)

if len(sys.argv) != 4:
    logger.error("Usage: %s <project> <site> <scheduler_id>", sys.argv[0])
    sys.exit(1)

project = sys.argv[1]
site = sys.argv[2]
scheduler_id = sys.argv[3]

# Dashboard: mark run as started
crawl_status.set_current_run(project, site, scheduler_id)

commands = [
    [sys.executable, "-m", "sdf_module.url_discovery", project, site, scheduler_id],
    [sys.executable, "-m", "sdf_module.url_retriever", project, site, scheduler_id],
    [sys.executable, "-m", "sdf_module.url_parser", project, site, scheduler_id],
]

stage_names = ["discovery", "retriever", "parser"]
for stage, cmd in zip(stage_names, commands):
    logger.info("[schedule_id=%s] Starting stage: %s", scheduler_id, stage)
    crawl_status.update_progress(project, site, scheduler_id, stage=stage)
    logger.debug("Running command: %s", cmd)
    result = subprocess.run(cmd)

    if result.returncode != 0:
        logger.error("[schedule_id=%s] Failed stage: %s", scheduler_id, stage)
        crawl_status.complete_current_run(status="failed")
        sys.exit(result.returncode)
    logger.info("[schedule_id=%s] Completed stage: %s", scheduler_id, stage)

crawl_status.complete_current_run(status="completed")
print(f"[schedule_id={scheduler_id}] Pipeline completed successfully")
