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
# Sync rate limiter (no Redis — simple in-process sleep)
# Used by existing sync workers where Redis is not available.
# ---------------------------------------------------------------------------

class SyncDomainRateLimiter:
    """In-process rate limiter using a per-domain timestamp dict."""

    def __init__(self):
        self._last: dict[str, float] = {}

    def acquire(self, domain: str) -> None:
        import random
        import time as _time

        d = domain.removeprefix("www.")
        delay = get_delay(d)
        last = self._last.get(d, 0.0)
        elapsed = _time.time() - last
        if elapsed < delay:
            wait = delay - elapsed + random.uniform(0.1, 0.5)
            _time.sleep(wait)
        self._last[d] = _time.time()
