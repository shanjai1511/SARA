"""
SARA — Smart proxy manager.

Features:
  - Tier-based proxy selection (residential → datacenter → direct)
  - Per-proxy, per-domain success/failure tracking
  - Automatic health-based weight decay
  - Consistent domain→proxy affinity (same domain always hits same proxy shard)
  - Works with existing Webshare proxy list format: [host, port, user, pass]

Usage:
    mgr = ProxyManager.from_env()          # reads WEBSHARE_PROXY_JSON
    proxy_url = mgr.get_proxy("myntra.com")
    # → "http://user:pass@host:port"
    mgr.report_success("myntra.com", proxy_url)
    mgr.report_failure("myntra.com", proxy_url, blocked=True)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)


class ProxyTier(Enum):
    RESIDENTIAL = "residential"   # Webshare rotating — primary
    DATACENTER  = "datacenter"    # Cheaper, detectable
    DIRECT      = "direct"        # No proxy — last resort


@dataclass
class ProxyEntry:
    url: str                            # http://user:pass@host:port
    tier: ProxyTier = ProxyTier.RESIDENTIAL
    requests: int = 0
    successes: int = 0
    failures: int = 0
    blocked_domains: set[str] = field(default_factory=set)
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.requests == 0:
            return 1.0
        return self.successes / self.requests

    @property
    def weight(self) -> float:
        """Sampling weight — decayed by failure rate."""
        if self.requests < 5:
            return 1.0   # Not enough data; treat as healthy
        return max(0.05, self.success_rate)

    def is_blocked_for(self, domain: str) -> bool:
        return domain in self.blocked_domains


class ProxyManager:
    """
    Thread-safe proxy manager with health tracking and automatic rotation.
    """

    def __init__(self, proxies: list[ProxyEntry]):
        self._proxies = proxies
        self._lock = Lock()

    # ── Factory ────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "ProxyManager":
        """Build from WEBSHARE_PROXY_JSON env var (existing format)."""
        raw = os.environ.get("WEBSHARE_PROXY_JSON", "")
        if not raw:
            logger.warning("WEBSHARE_PROXY_JSON not set — using direct connections")
            return cls([])
        proxy_list = json.loads(raw)
        entries = []
        for item in proxy_list:
            host, port, user, pwd = item
            url = f"http://{user}:{pwd}@{host}:{port}"
            entries.append(ProxyEntry(url=url, tier=ProxyTier.RESIDENTIAL))
        logger.info("ProxyManager: loaded %d proxies", len(entries))
        return cls(entries)

    @classmethod
    def from_list(cls, proxy_list: list[list]) -> "ProxyManager":
        """Build from a [[host, port, user, pass], ...] list."""
        entries = []
        for item in proxy_list:
            host, port, user, pwd = item
            url = f"http://{user}:{pwd}@{host}:{port}"
            entries.append(ProxyEntry(url=url, tier=ProxyTier.RESIDENTIAL))
        return cls(entries)

    # ── Selection ──────────────────────────────────────────────────────────

    def get_proxy(
        self,
        domain: str,
        tier: ProxyTier = ProxyTier.RESIDENTIAL,
        exclude: Optional[str] = None,
    ) -> Optional[str]:
        """
        Return a proxy URL for domain.
        - Uses consistent hashing for domain affinity (same domain → same shard)
        - Falls back to random weighted selection if affinity proxy is unhealthy
        - Returns None if no proxies available → caller uses direct connection
        """
        with self._lock:
            candidates = [
                p for p in self._proxies
                if p.tier == tier
                and not p.is_blocked_for(domain)
                and p.url != exclude
            ]
            if not candidates:
                return None

            # Consistent affinity: hash domain to a shard index
            shard = int(hashlib.md5(domain.encode()).hexdigest(), 16) % len(candidates)
            primary = candidates[shard]

            # Use primary if healthy
            if primary.weight >= 0.5:
                primary.last_used = time.time()
                return primary.url

            # Primary degraded — weighted random fallback
            weights = [c.weight for c in candidates]
            chosen = random.choices(candidates, weights=weights)[0]
            chosen.last_used = time.time()
            return chosen.url

    def get_proxy_for_request(self, domain: str) -> Optional[str]:
        """Convenience: try residential first, then datacenter, then None."""
        proxy = self.get_proxy(domain, tier=ProxyTier.RESIDENTIAL)
        if proxy is None:
            proxy = self.get_proxy(domain, tier=ProxyTier.DATACENTER)
        return proxy  # None → direct

    # ── Feedback ───────────────────────────────────────────────────────────

    def report_success(self, domain: str, proxy_url: str) -> None:
        with self._lock:
            entry = self._find(proxy_url)
            if entry:
                entry.requests += 1
                entry.successes += 1

    def report_failure(
        self,
        domain: str,
        proxy_url: str,
        blocked: bool = False,
    ) -> None:
        """
        Record a failure.
        If blocked=True (HTTP 403 / bot detection), mark this proxy as
        blocked for the domain — it won't be used for that domain again.
        """
        with self._lock:
            entry = self._find(proxy_url)
            if entry:
                entry.requests += 1
                entry.failures += 1
                if blocked:
                    entry.blocked_domains.add(domain.removeprefix("www."))
                    logger.warning(
                        "Proxy %s blocked on %s (success_rate=%.2f)",
                        proxy_url[:30], domain, entry.success_rate,
                    )

    def rotate_blocked(self, domain: str) -> Optional[str]:
        """Get a fresh proxy for a domain, excluding all blocked ones."""
        with self._lock:
            candidates = [
                p for p in self._proxies
                if not p.is_blocked_for(domain.removeprefix("www."))
            ]
            if not candidates:
                return None
            return random.choice(candidates).url

    # ── Stats ──────────────────────────────────────────────────────────────

    def health_report(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "url": p.url[:40] + "…",
                    "tier": p.tier.value,
                    "requests": p.requests,
                    "success_rate": round(p.success_rate, 3),
                    "blocked_domains": len(p.blocked_domains),
                    "weight": round(p.weight, 3),
                }
                for p in self._proxies
            ]

    def stats(self) -> dict:
        with self._lock:
            total = len(self._proxies)
            healthy = sum(1 for p in self._proxies if p.weight >= 0.5)
            return {
                "total": total,
                "healthy": healthy,
                "degraded": total - healthy,
                "avg_success_rate": (
                    sum(p.success_rate for p in self._proxies) / total
                    if total else 0.0
                ),
            }

    # ── Private ────────────────────────────────────────────────────────────

    def _find(self, url: str) -> Optional[ProxyEntry]:
        for p in self._proxies:
            if p.url == url:
                return p
        return None
