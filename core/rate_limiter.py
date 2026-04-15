"""
SARA — Per-domain rate limiter.

Implements a Redis-backed sliding-window rate limiter so that all worker
pods collectively respect per-domain crawl politeness policies.

Usage (async):
    limiter = DomainRateLimiter(redis_client)
    await limiter.acquire("myntra.com")   # waits if needed, then returns
    # → safe to make request

Usage (sync — for existing workers):
    limiter = SyncDomainRateLimiter(domain_policies)
    limiter.acquire("myntra.com")
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-domain crawl delay configuration (seconds between requests)
# Override via YAML config or environment; these are conservative defaults.
# ---------------------------------------------------------------------------
DOMAIN_POLICIES: dict[str, float] = {
    "myntra.com":              2.0,
    "flipkart.com":            1.5,
    "ajio.com":                3.0,
    "meesho.com":              2.5,
    "nykaa.com":               2.0,
    "shoppersstop.com":        3.0,
    "tatacliq.com":            2.0,
    "limeroad.com":            3.0,
    "max-fashion.com":         2.0,
    "businessoffashion.com":   1.0,
    "drapers.com":             1.0,
    "fashionunited.in":        1.0,
    "fashionunited.com":       1.0,
    "wwd.com":                 2.0,
    "fibre2fashion.com":       1.5,
    "apparelresources.com":    1.5,
    "juststyle.com":           2.0,
    "theindustryfashion.com":  1.0,
    "thefashionlaw.com":       1.0,
    "vogue.in":                2.0,
    "default":                 2.0,
}


def get_delay(domain: str) -> float:
    """Return the configured crawl delay (seconds) for a domain."""
    # Strip www. prefix for lookup
    d = domain.removeprefix("www.")
    return DOMAIN_POLICIES.get(d, DOMAIN_POLICIES["default"])


# ---------------------------------------------------------------------------
# Async rate limiter (Redis-backed, shared across all pods)
# ---------------------------------------------------------------------------

class DomainRateLimiter:
    """
    Sliding-window rate limiter stored in Redis.
    All worker pods share the same state — per-domain politeness is global.
    """

    def __init__(self, redis: "Redis"):
        self.redis = redis

    async def acquire(self, domain: str, jitter: float = 0.3) -> None:
        """
        Block until it is safe to make a request to domain.
        Adds a small random jitter to avoid synchronized thundering herds.
        """
        import random

        key = f"sara:ratelimit:{domain.removeprefix('www.')}"
        delay = get_delay(domain)

        while True:
            now = time.time()
            last_raw = await self.redis.get(key)
            if last_raw is None:
                # First request to this domain — grab the slot
                await self.redis.set(key, now, ex=int(delay) + 2)
                return

            last = float(last_raw)
            elapsed = now - last
            if elapsed >= delay:
                # Slot available — update and proceed
                new_ts = now + random.uniform(0, jitter)
                await self.redis.set(key, new_ts, ex=int(delay) + 2)
                return

            # Wait for the remaining window
            wait = (delay - elapsed) + random.uniform(0, jitter)
            logger.debug("Rate limit: sleeping %.2fs for %s", wait, domain)
            await asyncio.sleep(wait)

    async def reset(self, domain: str) -> None:
        """Clear the rate limit slot for a domain (use after proxy change)."""
        await self.redis.delete(f"sara:ratelimit:{domain.removeprefix('www.')}")


# ---------------------------------------------------------------------------
# Sync rate limiter (Redis-backed when available, in-process fallback)
# ---------------------------------------------------------------------------

class SyncDomainRateLimiter:
    """
    Per-domain rate limiter for synchronous workers.

    When REDIS_URL is set:
      - Uses Redis as the shared clock so ALL worker processes on ALL servers
        collectively respect each domain's delay.  Without this, 8 workers
        running concurrently could hit the same domain 8× too fast.
      - Key: sara:ratelimit:{domain}  →  last-request timestamp (float)
        TTL = delay + 5s (auto-expires idle domains)

    When Redis is unavailable:
      - Falls back to in-process timestamp dict.  Rate limits are per-process
        only — correct for single-worker deployments.
    """

    def __init__(self):
        self._last:  dict[str, float] = {}  # in-process fallback
        self._redis = None
        self._lock  = time   # placeholder; real lock created below
        import threading as _thr
        self._lock = _thr.Lock()
        self._try_redis()

    def _try_redis(self) -> None:
        try:
            from config.settings import settings as _s
            if not _s.REDIS_URL:
                return
            import redis as _rl
            client = _rl.Redis.from_url(
                _s.REDIS_URL, decode_responses=True,
                socket_timeout=0.5, socket_connect_timeout=0.5,
            )
            client.ping()
            self._redis = client
            logger.info("SyncDomainRateLimiter: using Redis backend (cross-process)")
        except Exception as exc:
            logger.debug("SyncDomainRateLimiter: Redis unavailable (%s) — in-process only", exc)

    def acquire(self, domain: str) -> None:
        import random
        import time as _t

        d     = domain.removeprefix("www.")
        delay = get_delay(d)

        if self._redis is not None:
            # ── Redis-backed: shared across all processes on all servers ──────
            key = f"sara:ratelimit:{d}"
            while True:
                now = _t.time()
                try:
                    last_raw = self._redis.get(key)
                except Exception:
                    # Redis I/O error — fall through to in-process
                    break
                if last_raw is None:
                    try:
                        self._redis.set(key, now, ex=int(delay) + 5)
                    except Exception:
                        pass
                    return
                last    = float(last_raw)
                elapsed = now - last
                if elapsed >= delay:
                    jitter = random.uniform(0.05, 0.3)
                    try:
                        self._redis.set(key, now + jitter, ex=int(delay) + 5)
                    except Exception:
                        pass
                    return
                wait = (delay - elapsed) + random.uniform(0.05, 0.3)
                logger.debug("RateLimiter[redis]: sleeping %.2fs for %s", wait, d)
                _t.sleep(wait)
            return

        # ── In-process fallback ───────────────────────────────────────────────
        with self._lock:
            last    = self._last.get(d, 0.0)
            elapsed = _t.time() - last
            if elapsed < delay:
                wait = delay - elapsed + random.uniform(0.1, 0.5)
                _t.sleep(wait)
            self._last[d] = _t.time()

    def reset(self, domain: str) -> None:
        """Clear rate limit for a domain (e.g. after proxy rotation)."""
        d = domain.removeprefix("www.")
        with self._lock:
            self._last.pop(d, None)
        if self._redis:
            try:
                self._redis.delete(f"sara:ratelimit:{d}")
            except Exception:
                pass
