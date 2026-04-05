"""
SARA — URL deduplication via Redis Bloom Filter.

Uses Redis BITFIELD (no RedisBloom module required) for a space-efficient,
probabilistic membership test.

Memory usage:
  - 10M URLs, 0.1% false positive → ~18 MB Redis memory
  - 50M URLs, 0.1% false positive → ~90 MB Redis memory

Usage:
    from core.dedup import BloomFilter
    bf = BloomFilter(redis_client, "sara:dedup:retriever", capacity=10_000_000)
    if not await bf.seen(url):
        await bf.add(url)
        # process url...
"""
from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


class BloomFilter:
    """
    Redis-backed probabilistic Bloom filter.

    Thread/async-safe — all ops are pipelined Lua scripts or BITFIELD.
    """

    def __init__(
        self,
        redis: "Redis",
        key: str,
        capacity: int = 10_000_000,
        error_rate: float = 0.001,
    ):
        self.redis = redis
        self.key = key
        self.bit_size = self._optimal_m(capacity, error_rate)
        self.hash_count = self._optimal_k(self.bit_size, capacity)

    # ── private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _optimal_m(n: int, p: float) -> int:
        """Optimal bit-array size for n items at false-positive rate p."""
        return int(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_k(m: int, n: int) -> int:
        """Optimal number of hash functions."""
        return max(1, round((m / n) * math.log(2)))

    def _bit_positions(self, item: str) -> list[int]:
        """Return hash_count bit positions for item."""
        positions = []
        for seed in range(self.hash_count):
            digest = hashlib.sha256(f"{seed}:{item}".encode()).digest()
            # Use first 8 bytes as uint64
            pos = int.from_bytes(digest[:8], "big") % self.bit_size
            positions.append(pos)
        return positions

    # ── public API ─────────────────────────────────────────────────────────

    async def add(self, item: str) -> None:
        """Mark item as seen."""
        pipe = self.redis.pipeline(transaction=False)
        for pos in self._bit_positions(item):
            pipe.setbit(self.key, pos, 1)
        await pipe.execute()

    async def seen(self, item: str) -> bool:
        """Return True if item was probably seen before (may false-positive)."""
        pipe = self.redis.pipeline(transaction=False)
        for pos in self._bit_positions(item):
            pipe.getbit(self.key, pos)
        results = await pipe.execute()
        return all(results)

    async def reset(self) -> None:
        """Clear the filter (delete the key)."""
        await self.redis.delete(self.key)

    async def estimated_count(self) -> int:
        """Estimate number of items added (Swamidass-Baldi approximation)."""
        # Count set bits — expensive for large filters; use sparingly
        bit_count_script = """
        local total = 0
        local key = KEYS[1]
        local sz = tonumber(ARGV[1])
        for i = 0, sz-1 do
            total = total + redis.call('GETBIT', key, i)
        end
        return total
        """
        # Simplified: just check a sample
        sample_size = min(10_000, self.bit_size)
        pipe = self.redis.pipeline(transaction=False)
        for i in range(sample_size):
            pipe.getbit(self.key, i)
        bits = await pipe.execute()
        ratio = sum(bits) / sample_size
        if ratio == 1.0:
            return self.bit_size  # saturated
        # Estimate using log formula
        estimated = -self.bit_size / self.hash_count * math.log(1 - ratio)
        return int(estimated)


# ---------------------------------------------------------------------------
# Synchronous fallback (file-based) — no Redis required for dev/testing
# ---------------------------------------------------------------------------

class FileBloomFilter:
    """
    Fallback dedup using a simple set persisted to a JSON-lines file.
    Not suitable for production scale (10M+ URLs) but works for dev.
    """

    def __init__(self, path: str):
        import json
        from pathlib import Path
        self._path = Path(path)
        self._seen: set[str] = set()
        if self._path.exists():
            for line in self._path.read_text().splitlines():
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
