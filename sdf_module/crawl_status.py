"""
Central read/write for crawl progress. Used by crawl_runner and stages
so the dashboard can show real-time progress.
"""
from .files_import import *
from pathlib import Path

STATUS_FILE = Path(base_dir) / "logs" / "crawl_status.json"
MAX_LAST_RUNS = 30


def _default() -> dict:
    return {"current_run": None, "last_runs": []}


def _ensure_logs_dir():
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_status() -> dict:
    """Read current status (current_run, last_runs). Safe to call from dashboard."""
    _ensure_logs_dir()
    if not STATUS_FILE.exists():
        return _default()
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("last_runs", [])
            return data
    except (json.JSONDecodeError, IOError):
        return _default()


def _write(data: dict) -> None:
    _ensure_logs_dir()
    tmp = STATUS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(STATUS_FILE)


def set_current_run(project: str, site: str, schedule_id: str) -> None:
    """Call at start of pipeline (crawl_runner)."""
    data = get_status()
    data["current_run"] = {
        "project": project,
        "site": site,
        "schedule_id": schedule_id,
        "stage": "discovery",
        "started_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "progress": {},
    }
    _write(data)


def update_progress(
    project: str,
    site: str,
    schedule_id: str,
    stage: str | None = None,
    **progress_kwargs: Any,
) -> None:
    """Update current run stage and/or progress. Called by runner and stages."""
    data = get_status()
    run = data.get("current_run")
    if not run:
        return
    if (
        run.get("project") != project
        or run.get("site") != site
        or run.get("schedule_id") != schedule_id
    ):
        return
    if stage is not None:
        run["stage"] = stage
    p = run.setdefault("progress", {})
    for k, v in progress_kwargs.items():
        if v is not None:
            p[k] = v
    _write(data)


def complete_current_run(status: str = "completed") -> None:
    """Move current_run to last_runs and clear current_run. Call at end of pipeline."""
    data = get_status()
    run = data.get("current_run")
    if run:
        run["completed_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        run["status"] = status
        data.setdefault("last_runs", []).insert(0, run)
        data["last_runs"] = data["last_runs"][:MAX_LAST_RUNS]
    data["current_run"] = None
    _write(data)
