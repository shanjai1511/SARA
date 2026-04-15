"""
Central read/write for crawl progress.

Dual-write strategy:
  1. Always write to local JSON (backward compat, works without Redis)
  2. If REDIS_URL is set, also write to Redis.

On read (get_status):
  - Reads Redis first → sees ALL workers across ALL servers
  - Falls back to local JSON if Redis unavailable

Redis key scheme:
  sara:crawl:current:{run_key}   → JSON, TTL=12h (auto-expires stale runs)
  sara:crawl:last_runs           → Redis list, capped at MAX_LAST_RUNS

File locking: cross-process file lock (fcntl/no-op on Windows) + in-process
threading.Lock for writes to the local JSON file.
"""
from .files_import import *
from pathlib import Path
import threading

STATUS_FILE   = Path(base_dir) / "logs" / "crawl_status.json"
_LOCK_FILE    = Path(base_dir) / "logs" / "crawl_status.lock"
MAX_LAST_RUNS = 50

_REDIS_TTL      = 12 * 3600   # seconds before a current-run key auto-expires
_REDIS_KEY_PFX  = "sara:crawl:current:"
_REDIS_LAST_KEY = "sara:crawl:last_runs"

# In-process lock — protects threads within the same Python process
_thread_lock = threading.Lock()


# ── Redis singleton ────────────────────────────────────────────────────────────

_redis      = None
_redis_ok   = False
_redis_lock = threading.Lock()


def _get_redis():
    """Return a Redis client or None (cached after first attempt)."""
    global _redis, _redis_ok
    if _redis_ok:
        return _redis
    with _redis_lock:
        if _redis_ok:
            return _redis
        _redis_ok = True   # mark done even on failure (don't retry every call)
        try:
            from config.settings import settings as _s
            url = _s.REDIS_URL
            if not url:
                return None
            import redis as _rl
            client = _rl.Redis.from_url(
                url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
            )
            client.ping()
            _redis = client
            logging.getLogger(__name__).info("crawl_status: Redis backend connected")
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "crawl_status: Redis unavailable (%s) — local JSON only", exc
            )
    return _redis


# ── Redis helpers ──────────────────────────────────────────────────────────────

def _redis_write_current(run_key: str, run: dict) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(f"{_REDIS_KEY_PFX}{run_key}", _REDIS_TTL, json.dumps(run))
    except Exception:
        pass


def _redis_delete_current(run_key: str) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(f"{_REDIS_KEY_PFX}{run_key}")
    except Exception:
        pass


def _redis_push_last(run: dict) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        r.lpush(_REDIS_LAST_KEY, json.dumps(run))
        r.ltrim(_REDIS_LAST_KEY, 0, MAX_LAST_RUNS - 1)
    except Exception:
        pass


def _redis_read_all() -> dict | None:
    """
    Return merged {current_runs, last_runs} from Redis, or None if unavailable.
    Reading from Redis shows runs from ALL connected servers, not just this one.
    """
    r = _get_redis()
    if r is None:
        return None
    try:
        # All active runs across every server
        keys = r.keys(f"{_REDIS_KEY_PFX}*")
        current_runs = {}
        for k in keys:
            raw = r.get(k)
            if raw:
                run_key = k.removeprefix(_REDIS_KEY_PFX)
                current_runs[run_key] = json.loads(raw)

        # Recent completed runs
        raw_list = r.lrange(_REDIS_LAST_KEY, 0, MAX_LAST_RUNS - 1)
        last_runs = [json.loads(x) for x in raw_list if x]

        return {"current_runs": current_runs, "last_runs": last_runs}
    except Exception:
        return None


# ── cross-process file locking ─────────────────────────────────────────────────

def _acquire_file_lock():
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fp = open(_LOCK_FILE, "a+")
    try:
        import fcntl
        fcntl.flock(fp, fcntl.LOCK_EX)
    except ImportError:
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


# ── local JSON helpers ─────────────────────────────────────────────────────────

def _default() -> dict:
    return {"current_runs": {}, "last_runs": []}


def _run_key(project: str, site: str, schedule_id: str) -> str:
    return f"{project}__{site}__{schedule_id}"


def _ensure_logs_dir() -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_raw() -> dict:
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
    _ensure_logs_dir()
    save = {k: v for k, v in data.items() if k != "current_run"}
    tmp = STATUS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2)
    tmp.replace(STATUS_FILE)


# ── public API ─────────────────────────────────────────────────────────────────

def get_status() -> dict:
    """
    Return current pipeline status.

    Reads Redis first (shows ALL servers' data) and falls back to local JSON.
    The dashboard calls this — it will see workers from every connected server.
    """
    redis_data = _redis_read_all()

    if redis_data is not None:
        # Merge Redis data (all servers) with local data (this server)
        # Local data takes precedence for *this* server's runs (fresher).
        with _thread_lock:
            fp = _acquire_file_lock()
            try:
                local = _read_raw()
            finally:
                _release_file_lock(fp)

        # Merge: local runs overwrite Redis for same key (local is more up-to-date)
        merged_current = {**redis_data["current_runs"], **local["current_runs"]}
        merged_last    = local["last_runs"] or redis_data["last_runs"]
        data = {"current_runs": merged_current, "last_runs": merged_last}
    else:
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
            run  = {
                "project":     project,
                "site":        site,
                "schedule_id": schedule_id,
                "stage":       "discovery",
                "started_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "worker_id":   os.environ.get("WORKER_ID", "local"),
                "hostname":    _hostname(),
                "progress":    {},
            }
            data["current_runs"][key] = run
            _write_raw(data)
        finally:
            _release_file_lock(fp)

    _redis_write_current(key, run)


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
            run["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            data["current_runs"][key] = run
            _write_raw(data)
            _run_snapshot = dict(run)   # copy for Redis write outside lock
        finally:
            _release_file_lock(fp)

    _redis_write_current(key, _run_snapshot)


def complete_current_run(
    project: str | None = None,
    site: str | None = None,
    schedule_id: str | None = None,
    status: str = "completed",
) -> None:
    with _thread_lock:
        fp = _acquire_file_lock()
        try:
            data    = _read_raw()
            now     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            to_push = []   # (run_key, run) pairs to write to Redis

            if project and site and schedule_id:
                key = _run_key(project, site, schedule_id)
                run = data["current_runs"].pop(key, None)
                if run:
                    run["completed_at"] = now
                    run["status"]       = status
                    data.setdefault("last_runs", []).insert(0, run)
                    data["last_runs"] = data["last_runs"][:MAX_LAST_RUNS]
                    to_push.append((key, run))
            else:
                for k, run in list(data["current_runs"].items()):
                    run["completed_at"] = now
                    run["status"]       = status
                    data.setdefault("last_runs", []).insert(0, run)
                    to_push.append((k, run))
                data["current_runs"] = {}
                data["last_runs"]    = data["last_runs"][:MAX_LAST_RUNS]

            _write_raw(data)
        finally:
            _release_file_lock(fp)

    # Redis writes outside the file lock
    for run_key, run in to_push:
        _redis_delete_current(run_key)
        _redis_push_last(run)


# ── helpers ────────────────────────────────────────────────────────────────────

def _hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"
