from sdf_module.files_import import *

if len(sys.argv) != 4:
    print("Usage: python crawl_runner.py <project> <site> <scheduler_id>")
    sys.exit(1)

project = sys.argv[1]
site = sys.argv[2]
scheduler_id = sys.argv[3]

commands = [
    ["python", "-m", "sdf_module.url_discovery", project, site, scheduler_id],
    ["python", "-m", "sdf_module.url_retriever", project, site, scheduler_id],
    ["python", "-m", "sdf_module.url_parser", project, site, scheduler_id],
]

stage_names = ["discovery", "retriever", "parser"]
for stage, cmd in zip(stage_names, commands):
    print(f"[schedule_id={scheduler_id}] Starting stage: {stage}")
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"[schedule_id={scheduler_id}] Failed stage: {stage}")
        sys.exit(result.returncode)
    print(f"[schedule_id={scheduler_id}] Completed stage: {stage}")

print(f"[schedule_id={scheduler_id}] Pipeline completed successfully")
