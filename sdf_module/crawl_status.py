"""
Central read/write for crawl progress.

Fix 3: current_run changed to current_runs dict keyed by
"{project}__{site}__{schedule_id}" so concurrent crawls don't overwrite each other.

Backward compat: get_status() still exposes "current_run" (first active run)
so existing dashboard code keeps working unchanged.
"""
from .files_import import *
from pathlib import Path

STATUS_FILE = Path(base_dir) / "logs" / "crawl_status.json"
MAX_LAST_RUNS = 30


def _default() -> dict:
    return {"current_runs": {}, "last_runs": []}


def _run_key(project: str, site: str, schedule_id: str) -> str:
    return f"{project}__{site}__{schedule_id}"


def _ensure_logs_dir():
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_status() -> dict:
    """Read current status. Safe to call from dashboard."""
    _ensure_logs_dir()
    if not STATUS_FILE.exists():
        d = _default()
        d["current_run"] = None
        return d
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Migrate old single current_run format
        if "current_run" in data and "current_runs" not in data:
            old = data.pop("current_run")
            data["current_runs"] = {}
            if old:
                key = _run_key(old["project"], old["site"], old["schedule_id"])
                data["current_runs"][key] = old
        data.setdefault("current_runs", {})
        data.setdefault("last_runs", [])
        # Expose current_run (first active) for backward compat
        runs = list(data["current_runs"].values())
        data["current_run"] = runs[0] if runs else None
        return data
    except (json.JSONDecodeError, IOError):
        d = _default()
        d["current_run"] = None
        return d


def _write(data: dict) -> None:
    _ensure_logs_dir()
    # Don't persist the backward-compat alias
    save = {k: v for k, v in data.items() if k != "current_run"}
    tmp = STATUS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2)
    tmp.replace(STATUS_FILE)


def set_current_run(project: str, site: str, schedule_id: str) -> None:
    data = get_status()
    key = _run_key(project, site, schedule_id)
    data["current_runs"][key] = {
        "project": project,
        "site": site,
        "schedule_id": schedule_id,
        "stage": "discovery",
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    data = get_status()
    key = _run_key(project, site, schedule_id)
    run = data["current_runs"].get(key)
    if not run:
        return
    if stage is not None:
        run["stage"] = stage
    p = run.setdefault("progress", {})
    for k, v in progress_kwargs.items():
        if v is not None:
            p[k] = v
    data["current_runs"][key] = run
    _write(data)


def complete_current_run(
    project: str | None = None,
    site: str | None = None,
    schedule_id: str | None = None,
    status: str = "completed",
) -> None:
    """Move a current run to last_runs. Accepts explicit keys or clears all if none given."""
    data = get_status()

    if project and site and schedule_id:
        key = _run_key(project, site, schedule_id)
        run = data["current_runs"].pop(key, None)
        if run:
            run["completed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run["status"] = status
            data.setdefault("last_runs", []).insert(0, run)
            data["last_runs"] = data["last_runs"][:MAX_LAST_RUNS]
    else:
        # Legacy: clear all (called without args)
        for run in list(data["current_runs"].values()):
            run["completed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            run["status"] = status
            data.setdefault("last_runs", []).insert(0, run)
        data["current_runs"] = {}
        data["last_runs"] = data["last_runs"][:MAX_LAST_RUNS]

    _write(data)
