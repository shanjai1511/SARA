"""
Central read/write for crawl progress.

Fix 3 (previous): current_runs dict keyed by project__site__schedule_id
Fix 4 (this):     file-level locking so concurrent crawl processes don't
                  corrupt crawl_status.json.

Locking strategy:
  - A companion lock file (.lock) is acquired with an exclusive flock before
    every read-modify-write cycle.
  - An in-process threading.Lock serialises threads within the same process.
  - Both locks are always released even if an exception occurs.
"""
from .files_import import *
from pathlib import Path
import threading

STATUS_FILE = Path(base_dir) / "logs" / "crawl_status.json"
_LOCK_FILE  = Path(base_dir) / "logs" / "crawl_status.lock"
MAX_LAST_RUNS = 50   # keep more history now that concurrent crawls fill it faster

# In-process lock — protects threads within the same Python process
_thread_lock = threading.Lock()


# ── cross-process file locking ─────────────────────────────────────────────────

def _acquire_file_lock():
    """Return an open, exclusively-locked file handle. Caller must release it."""
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fp = open(_LOCK_FILE, "a+")
    try:
        import fcntl
        fcntl.flock(fp, fcntl.LOCK_EX)
    except ImportError:
        # Windows: fcntl not available; threading.Lock is sufficient for
        # single-machine deployments without multi-process contention.
        pass
    return fp


def _release_file_lock(fp) -> None:
    try:
        import fcntl
        fcntl.flock(fp, fcntl.LOCK_UN)
    except ImportError:
        pass
    finally:
        try:
            fp.close()
        except Exception:
            pass


# ── internal helpers ───────────────────────────────────────────────────────────

def _default() -> dict:
    return {"current_runs": {}, "last_runs": []}


def _run_key(project: str, site: str, schedule_id: str) -> str:
    return f"{project}__{site}__{schedule_id}"


def _ensure_logs_dir() -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_raw() -> dict:
    """Read status file without locking — caller must hold both locks."""
    _ensure_logs_dir()
    if not STATUS_FILE.exists():
        return _default()
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
        return data
    except (json.JSONDecodeError, IOError):
        return _default()


def _write_raw(data: dict) -> None:
    """Write status file without locking — caller must hold both locks."""
    _ensure_logs_dir()
    save = {k: v for k, v in data.items() if k != "current_run"}
    tmp  = STATUS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2)
    tmp.replace(STATUS_FILE)


# ── public API ─────────────────────────────────────────────────────────────────

def get_status() -> dict:
    """Read current status. Safe to call from the dashboard (read-only)."""
    with _thread_lock:
        fp = _acquire_file_lock()
        try:
            data = _read_raw()
        finally:
            _release_file_lock(fp)

    runs = list(data["current_runs"].values())
    data["current_run"] = runs[0] if runs else None   # backward-compat alias
    return data


def set_current_run(project: str, site: str, schedule_id: str) -> None:
    with _thread_lock:
        fp = _acquire_file_lock()
        try:
            data = _read_raw()
            key  = _run_key(project, site, schedule_id)
            data["current_runs"][key] = {
                "project":     project,
                "site":        site,
                "schedule_id": schedule_id,
                "stage":       "discovery",
                "started_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "progress":    {},
            }
            _write_raw(data)
        finally:
            _release_file_lock(fp)


def update_progress(
    project: str,
    site: str,
    schedule_id: str,
    stage: str | None = None,
    **progress_kwargs: Any,
) -> None:
    with _thread_lock:
        fp = _acquire_file_lock()
        try:
            data = _read_raw()
            key  = _run_key(project, site, schedule_id)
            run  = data["current_runs"].get(key)
            if not run:
                _release_file_lock(fp)
                return
            if stage is not None:
                run["stage"] = stage
            p = run.setdefault("progress", {})
            for k, v in progress_kwargs.items():
                if v is not None:
                    p[k] = v
            data["current_runs"][key] = run
            _write_raw(data)
        finally:
            _release_file_lock(fp)


def complete_current_run(
    project: str | None = None,
    site: str | None = None,
    schedule_id: str | None = None,
    status: str = "completed",
) -> None:
    with _thread_lock:
        fp = _acquire_file_lock()
        try:
            data = _read_raw()
            now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            if project and site and schedule_id:
                key = _run_key(project, site, schedule_id)
                run = data["current_runs"].pop(key, None)
                if run:
                    run["completed_at"] = now
                    run["status"]       = status
                    data.setdefault("last_runs", []).insert(0, run)
                    data["last_runs"] = data["last_runs"][:MAX_LAST_RUNS]
            else:
                for run in list(data["current_runs"].values()):
                    run["completed_at"] = now
                    run["status"]       = status
                    data.setdefault("last_runs", []).insert(0, run)
                data["current_runs"] = {}
                data["last_runs"]    = data["last_runs"][:MAX_LAST_RUNS]

            _write_raw(data)
        finally:
            _release_file_lock(fp)
