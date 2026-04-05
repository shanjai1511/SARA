"""
SARA — Content-change detection.

Tracks the MD5 hash of every fetched page.  Before writing parsed records,
the parser worker checks whether the page content has actually changed.
This prevents redundant DB writes and downstream noise.

Storage backends:
  FileChangeStore    — JSON-file backed (dev / single node)
  RedisChangeStore   — Redis-backed (multi-node, TTL-aware)

Usage:
    store = FileChangeStore(path="logs/change_state.json")
    result = store.check_and_update(url, new_html)
    if result.changed:
        # parse and save the record
        print(result.change_type)   # "new" | "modified" | "unchanged"
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    NEW       = "new"        # URL never seen before
    MODIFIED  = "modified"   # Content hash changed
    UNCHANGED = "unchanged"  # Same hash as last crawl


@dataclass
class ChangeResult:
    url: str
    change_type: ChangeType
    old_hash: Optional[str]
    new_hash: str
    changed: bool  # convenience: True for NEW or MODIFIED

    @classmethod
    def unchanged(cls, url: str, h: str) -> "ChangeResult":
        return cls(url=url, change_type=ChangeType.UNCHANGED,
                   old_hash=h, new_hash=h, changed=False)

    @classmethod
    def new(cls, url: str, h: str) -> "ChangeResult":
        return cls(url=url, change_type=ChangeType.NEW,
                   old_hash=None, new_hash=h, changed=True)

    @classmethod
    def modified(cls, url: str, old: str, new: str) -> "ChangeResult":
        return cls(url=url, change_type=ChangeType.MODIFIED,
                   old_hash=old, new_hash=new, changed=True)


def _html_hash(html: str) -> str:
    """MD5 of HTML content — fast, good enough for change detection."""
    return hashlib.md5(html.encode("utf-8", errors="replace")).hexdigest()


# ---------------------------------------------------------------------------
# File-backed store (development / single-node)
# ---------------------------------------------------------------------------

class FileChangeStore:
    """
    Persists URL→hash mapping in a JSON file.
    Thread-safe writes (lock + atomic replace).
    Not suitable for multi-pod deployments — use RedisChangeStore instead.
    """

    def __init__(self, path: str | Path = "logs/change_state.json"):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def check_and_update(self, url: str, html: str) -> ChangeResult:
        new_hash = _html_hash(html)
        with self._lock:
            entry = self._data.get(url)
            if entry is None:
                self._data[url] = {
                    "hash": new_hash,
                    "first_seen": time.time(),
                    "last_crawled": time.time(),
                    "change_count": 0,
                }
                self._save()
                return ChangeResult.new(url, new_hash)

            old_hash = entry["hash"]
            entry["last_crawled"] = time.time()
            if old_hash == new_hash:
                self._save()
                return ChangeResult.unchanged(url, new_hash)

            entry["hash"] = new_hash
            entry["change_count"] = entry.get("change_count", 0) + 1
            self._save()
            return ChangeResult.modified(url, old_hash, new_hash)

    def get_hash(self, url: str) -> Optional[str]:
        with self._lock:
            entry = self._data.get(url)
            return entry["hash"] if entry else None

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_urls": len(self._data),
                "total_changes": sum(
                    e.get("change_count", 0) for e in self._data.values()
                ),
            }


# ---------------------------------------------------------------------------
# Redis-backed store (multi-pod, production)
# ---------------------------------------------------------------------------

class RedisChangeStore:
    """
    URL→hash mapping in Redis with optional TTL.

    Key: sara:hash:{md5_of_url}
    Value: JSON {"hash": "...", "first_seen": ts, "last_crawled": ts, "change_count": n}
    TTL: 30 days (refresh on each crawl) — purges stale/deleted URLs automatically
    """

    KEY_TTL = 30 * 24 * 3600   # 30 days

    def __init__(self, redis):
        self.redis = redis

    def _key(self, url: str) -> str:
        return f"sara:hash:{hashlib.md5(url.encode()).hexdigest()}"

    async def check_and_update(self, url: str, html: str) -> ChangeResult:
        new_hash = _html_hash(html)
        key = self._key(url)
        now = time.time()

        raw = await self.redis.get(key)
        if raw is None:
            entry = {
                "hash": new_hash,
                "first_seen": now,
                "last_crawled": now,
                "change_count": 0,
            }
            await self.redis.setex(key, self.KEY_TTL, json.dumps(entry))
            return ChangeResult.new(url, new_hash)

        entry = json.loads(raw)
        old_hash = entry["hash"]
        entry["last_crawled"] = now

        if old_hash == new_hash:
            await self.redis.setex(key, self.KEY_TTL, json.dumps(entry))
            return ChangeResult.unchanged(url, new_hash)

        entry["hash"] = new_hash
        entry["change_count"] = entry.get("change_count", 0) + 1
        await self.redis.setex(key, self.KEY_TTL, json.dumps(entry))
        return ChangeResult.modified(url, old_hash, new_hash)

    async def get_hash(self, url: str) -> Optional[str]:
        raw = await self.redis.get(self._key(url))
        if raw:
            return json.loads(raw).get("hash")
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_change_store(redis=None, path: str | Path = "logs/change_state.json"):
    """Return appropriate change store based on available deps."""
    if redis is not None:
        return RedisChangeStore(redis)
    return FileChangeStore(path=path)
