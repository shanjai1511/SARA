"""
SARA — URL deduplication.

Three implementations — pick the right one for your environment:

  BloomFilter       async, Redis-backed  — production (high scale)
  SyncBloomFilter   sync,  Redis-backed  — used by sync retriever workers
  FileBloomFilter   sync,  file-backed   — dev / no-Redis fallback

Factory:
    from core.dedup import get_sync_dedup
    dedup = get_sync_dedup("commerce_crawl", "myntra_com")
    if not dedup.seen_sync(url):
        dedup.add_sync(url)
        # fetch url ...

Memory usage (Redis Bloom filter):
  10M URLs, 0.1% FP rate  →  ~18 MB Redis memory
  50M URLs, 0.1% FP rate  →  ~90 MB Redis memory
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis


# ── helpers ────────────────────────────────────────────────────────────────────

def _optimal_m(n: int, p: float) -> int:
    """Optimal bit-array size for n items at false-positive rate p."""
    return int(-n * math.log(p) / (math.log(2) ** 2))


def _optimal_k(m: int, n: int) -> int:
    """Optimal number of hash functions."""
    return max(1, round((m / n) * math.log(2)))


def _bit_positions(item: str, hash_count: int, bit_size: int) -> list[int]:
    positions = []
    for seed in range(hash_count):
        digest = hashlib.sha256(f"{seed}:{item}".encode()).digest()
        pos = int.from_bytes(digest[:8], "big") % bit_size
        positions.append(pos)
    return positions


# ── async Bloom filter (production, Redis) ────────────────────────────────────

class BloomFilter:
    """
    Async Redis-backed Bloom filter. Use with async workers / FastAPI.

    Thread/async-safe — all ops are pipelined.
    """

    def __init__(
        self,
        redis: "AsyncRedis",
        key: str,
        capacity: int = 10_000_000,
        error_rate: float = 0.001,
    ):
        self.redis = redis
        self.key = key
        self.bit_size = _optimal_m(capacity, error_rate)
        self.hash_count = _optimal_k(self.bit_size, capacity)

    async def add(self, item: str) -> None:
        pipe = self.redis.pipeline(transaction=False)
        for pos in _bit_positions(item, self.hash_count, self.bit_size):
            pipe.setbit(self.key, pos, 1)
        await pipe.execute()

    async def seen(self, item: str) -> bool:
        pipe = self.redis.pipeline(transaction=False)
        for pos in _bit_positions(item, self.hash_count, self.bit_size):
            pipe.getbit(self.key, pos)
        results = await pipe.execute()
        return all(results)

    async def reset(self) -> None:
        await self.redis.delete(self.key)

    async def estimated_count(self) -> int:
        sample_size = min(10_000, self.bit_size)
        pipe = self.redis.pipeline(transaction=False)
        for i in range(sample_size):
            pipe.getbit(self.key, i)
        bits = await pipe.execute()
        ratio = sum(bits) / sample_size
        if ratio == 1.0:
            return self.bit_size
        estimated = -self.bit_size / self.hash_count * math.log(1 - ratio)
        return int(estimated)


# ── sync Bloom filter (Fix 7: used by sync retriever workers) ─────────────────

class SyncBloomFilter:
    """
    Synchronous Redis-backed Bloom filter for use in threaded workers.

    Uses the standard `redis` client (not redis.asyncio).
    Thread-safe — Redis pipeline operations are atomic per call.
    """

    def __init__(
        self,
        redis_client,   # redis.Redis instance
        key: str,
        capacity: int = 10_000_000,
        error_rate: float = 0.001,
    ):
        self._redis = redis_client
        self.key = key
        self.bit_size = _optimal_m(capacity, error_rate)
        self.hash_count = _optimal_k(self.bit_size, capacity)

    def add_sync(self, item: str) -> None:
        pipe = self._redis.pipeline(transaction=False)
        for pos in _bit_positions(item, self.hash_count, self.bit_size):
            pipe.setbit(self.key, pos, 1)
        pipe.execute()

    def seen_sync(self, item: str) -> bool:
        pipe = self._redis.pipeline(transaction=False)
        for pos in _bit_positions(item, self.hash_count, self.bit_size):
            pipe.getbit(self.key, pos)
        results = pipe.execute()
        return all(results)

    def reset(self) -> None:
        self._redis.delete(self.key)


# ── file-based fallback (dev / no Redis) ──────────────────────────────────────

class FileBloomFilter:
    """
    Sync, file-persisted dedup using an in-memory set.
    Suitable for dev and small crawls (< 100 K URLs).
    Not suitable for 10M+ URLs (holds all URLs in RAM).
    """

    def __init__(self, path: str):
        import json
        self._path = Path(path)
        self._seen: set[str] = set()
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        self._seen.add(json.loads(line))
                    except Exception:
                        pass

    def add_sync(self, url: str) -> None:
        import json
        if url not in self._seen:
            self._seen.add(url)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(url) + "\n")

    def seen_sync(self, url: str) -> bool:
        return url in self._seen


# ── factory ───────────────────────────────────────────────────────────────────

def get_sync_dedup(
    project: str,
    site: str,
    capacity: int = 5_000_000,
) -> SyncBloomFilter | FileBloomFilter:
    """
    Return the best available sync dedup filter for a project/site pair.

    Priority:
      1. SyncBloomFilter (Redis) — if REDIS_URL is set
      2. FileBloomFilter         — fallback, persisted to logs/dedup/

    The Redis key is namespaced per project+site so different sites
    don't share dedup state, and the filter persists across crawl runs
    so URLs already fetched are not re-fetched next week.
    """
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis as _redis_lib
            client = _redis_lib.Redis.from_url(redis_url, decode_responses=False)
            client.ping()
            key = f"sara:dedup:{project}:{site}"
            return SyncBloomFilter(client, key, capacity=capacity)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Redis unavailable for dedup (%s) — falling back to FileBloomFilter", exc
            )

    # File fallback
    dedup_dir = Path(__file__).resolve().parent.parent / "logs" / "dedup"
    dedup_dir.mkdir(parents=True, exist_ok=True)
    return FileBloomFilter(str(dedup_dir / f"{project}__{site}.jsonl"))
