"""
SARA — Smart Proxy Manager  (v3)

Features:
  - Per-proxy circuit breaker: CLOSED → OPEN → HALF-OPEN → CLOSED
  - Exponential moving average (EMA) success rate — recent failures hurt more
  - Latency tracking: rolling P50 per proxy
  - Domain-level block registry: once a proxy is blocked on a domain it is
    never used for that domain again (until manually reset)
  - Redis-backed health state: shared across all worker processes and servers.
    If Redis is unavailable the manager falls back to in-process state.
  - Proxy tier priority: residential → datacenter → direct
  - Consistent domain affinity with automatic fallback when primary is degraded
  - `rotate_and_mark()`: one call to mark a proxy bad AND get the next one
  - Thread-safe for use in the sync retriever thread pool

Redis key scheme:
  sara:proxy:{hash8}:ema       → float  (EMA success rate, 0.0–1.0)
  sara:proxy:{hash8}:consec    → int    (consecutive failures, reset on success)
  sara:proxy:{hash8}:cooldown  → float  (Unix timestamp until cooldown expires)
  sara:proxy:{hash8}:latency   → float  (EMA latency ms)
  sara:proxy:{hash8}:blocked   → Redis SET of domain strings
  TTL on all keys: 48 h (auto-expires idle proxies)

Usage:
    mgr = ProxyManager.from_env()

    proxy_url = mgr.get_proxy("myntra.com")
    # → "http://user:pass@host:port"  or None (direct)

    # After request completes:
    mgr.report_success("myntra.com", proxy_url, latency_ms=320)
    mgr.report_failure("myntra.com", proxy_url, blocked=True)  # 403

    # Get next proxy after a block, marking the old one in one call:
    next_proxy = mgr.rotate_and_mark("myntra.com", failed_proxy_url, blocked=True)
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Optional
import os

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMA_ALPHA           = 0.15   # smoothing: 0.15 ≈ last 13 outcomes matter most
_CB_FAIL_THRESHOLD   = 4      # consecutive failures to open circuit
_CB_COOLDOWN_BASE    = 120.0  # seconds before HALF-OPEN probe
_CB_COOLDOWN_MAX     = 900.0  # cap cooldown at 15 min after repeated failures
_LATENCY_ALPHA       = 0.2    # EMA alpha for latency
_MIN_WEIGHT          = 0.05   # floor weight so circuit never fully starves
_DEGRADE_THRESHOLD   = 0.40   # below this EMA rate, proxy is "degraded"
_HEALTHY_THRESHOLD   = 0.70   # above this, proxy is "healthy"
_PROXY_KEY_TTL       = 48 * 3600   # Redis key TTL in seconds


class ProxyTier(Enum):
    RESIDENTIAL = "residential"
    DATACENTER  = "datacenter"
    DIRECT      = "direct"


class CBState(Enum):
    CLOSED    = "closed"     # normal operation
    OPEN      = "open"       # failing — skip until cooldown expires
    HALF_OPEN = "half_open"  # cooldown done — allow one probe


# ---------------------------------------------------------------------------
# Per-proxy state
# ---------------------------------------------------------------------------

@dataclass
class ProxyEntry:
    url:   str
    tier:  ProxyTier = ProxyTier.RESIDENTIAL

    # EMA success rate (0.0 = all failures, 1.0 = all successes)
    ema_rate:         float = 1.0
    # EMA latency in milliseconds
    ema_latency_ms:   float = 500.0

    # Circuit breaker
    consecutive_fails: int   = 0
    cooldown_until:    float = 0.0   # Unix timestamp; 0 = not in cooldown
    cooldown_mult:     int   = 1     # doubles on each consecutive OPEN trip

    # Domain-level block list
    blocked_domains: set[str] = field(default_factory=set)

    # Stats counters (for /health endpoint display only — not used for selection)
    total_requests:  int = 0
    total_successes: int = 0

    # Stable 8-char identifier derived from URL hash
    @property
    def key(self) -> str:
        return hashlib.md5(self.url.encode()).hexdigest()[:8]

    @property
    def cb_state(self) -> CBState:
        if self.consecutive_fails >= _CB_FAIL_THRESHOLD:
            if time.time() < self.cooldown_until:
                return CBState.OPEN
            return CBState.HALF_OPEN
        return CBState.CLOSED

    @property
    def weight(self) -> float:
        """
        Sampling weight for random selection.
        - OPEN proxies get weight 0 (never selected)
        - HALF_OPEN: allow probe (weight = _MIN_WEIGHT)
        - CLOSED: EMA rate, floored at _MIN_WEIGHT
        """
        state = self.cb_state
        if state == CBState.OPEN:
            return 0.0
        if state == CBState.HALF_OPEN:
            return _MIN_WEIGHT
        return max(_MIN_WEIGHT, self.ema_rate)

    @property
    def is_healthy(self) -> bool:
        return self.cb_state == CBState.CLOSED and self.ema_rate >= _HEALTHY_THRESHOLD

    @property
    def is_degraded(self) -> bool:
        return self.ema_rate < _DEGRADE_THRESHOLD

    def is_blocked_for(self, domain: str) -> bool:
        return domain.removeprefix("www.") in self.blocked_domains

    def record_success(self, latency_ms: float = 0.0) -> None:
        self.ema_rate          = _EMA_ALPHA * 1.0 + (1 - _EMA_ALPHA) * self.ema_rate
        self.consecutive_fails = 0
        self.cooldown_mult     = 1
        self.cooldown_until    = 0.0
        self.total_requests   += 1
        self.total_successes  += 1
        if latency_ms > 0:
            self.ema_latency_ms = (
                _LATENCY_ALPHA * latency_ms + (1 - _LATENCY_ALPHA) * self.ema_latency_ms
            )

    def record_failure(self, domain: str = "", blocked: bool = False) -> None:
        self.ema_rate          = _EMA_ALPHA * 0.0 + (1 - _EMA_ALPHA) * self.ema_rate
        self.consecutive_fails += 1
        self.total_requests   += 1

        if blocked and domain:
            self.blocked_domains.add(domain.removeprefix("www."))

        if self.consecutive_fails >= _CB_FAIL_THRESHOLD:
            cooldown = min(_CB_COOLDOWN_BASE * self.cooldown_mult, _CB_COOLDOWN_MAX)
            self.cooldown_until = time.time() + cooldown
            self.cooldown_mult  = min(self.cooldown_mult * 2, 8)
            logger.warning(
                "Proxy %s … circuit OPEN after %d failures — cooling down %.0fs",
                self.url[-30:], self.consecutive_fails, cooldown,
            )


# ---------------------------------------------------------------------------
# ProxyManager
# ---------------------------------------------------------------------------

class ProxyManager:
    """
    Thread-safe proxy manager with health tracking, circuit breaking,
    latency awareness, and optional Redis-backed shared state.
    """

    def __init__(self, proxies: list[ProxyEntry], redis_url: str = ""):
        self._proxies  = proxies
        self._lock     = Lock()
        self._redis    = None
        self._redis_ok = False

        if redis_url:
            self._init_redis(redis_url)
            if self._redis:
                self._load_redis_state()

    # ── Factory ────────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "ProxyManager":
        """Build from WEBSHARE_PROXY_JSON + REDIS_URL env vars."""
        raw       = os.environ.get("WEBSHARE_PROXY_JSON", "").strip()
        redis_url = os.environ.get("REDIS_URL", "").strip()

        entries: list[ProxyEntry] = []
        if raw and raw not in ("[]", ""):
            try:
                proxy_list = json.loads(raw)
                for item in proxy_list:
                    host, port, user, pwd = item
                    url = f"http://{user}:{pwd}@{host}:{port}"
                    entries.append(ProxyEntry(url=url, tier=ProxyTier.RESIDENTIAL))
                logger.info("ProxyManager: loaded %d proxies", len(entries))
            except Exception as exc:
                logger.error("Failed to parse WEBSHARE_PROXY_JSON: %s", exc)

        return cls(entries, redis_url=redis_url)

    @classmethod
    def from_list(cls, proxy_list: list[list], redis_url: str = "") -> "ProxyManager":
        entries = []
        for item in proxy_list:
            host, port, user, pwd = item
            entries.append(ProxyEntry(
                url=f"http://{user}:{pwd}@{host}:{port}",
                tier=ProxyTier.RESIDENTIAL,
            ))
        return cls(entries, redis_url=redis_url)

    # ── Redis init ─────────────────────────────────────────────────────────────

    def _init_redis(self, redis_url: str) -> None:
        try:
            import redis as _rl
            client = _rl.Redis.from_url(
                redis_url, decode_responses=True,
                socket_timeout=2, socket_connect_timeout=2,
            )
            client.ping()
            self._redis    = client
            self._redis_ok = True
            logger.info("ProxyManager: Redis backend connected (%d proxies)", len(self._proxies))
        except Exception as exc:
            logger.debug("ProxyManager: Redis unavailable (%s) — in-process state only", exc)

    def _proxy_redis_key(self, entry: ProxyEntry, field: str) -> str:
        return f"sara:proxy:{entry.key}:{field}"

    def _load_redis_state(self) -> None:
        """Restore health state from Redis on startup."""
        if not self._redis:
            return
        loaded = 0
        for entry in self._proxies:
            try:
                r = self._redis
                ema     = r.get(self._proxy_redis_key(entry, "ema"))
                consec  = r.get(self._proxy_redis_key(entry, "consec"))
                cool    = r.get(self._proxy_redis_key(entry, "cooldown"))
                latency = r.get(self._proxy_redis_key(entry, "latency"))
                blocked = r.smembers(self._proxy_redis_key(entry, "blocked"))

                if ema      is not None: entry.ema_rate          = float(ema)
                if consec   is not None: entry.consecutive_fails = int(consec)
                if cool     is not None: entry.cooldown_until    = float(cool)
                if latency  is not None: entry.ema_latency_ms    = float(latency)
                if blocked:              entry.blocked_domains   = set(blocked)
                loaded += 1
            except Exception:
                pass
        if loaded:
            logger.info("ProxyManager: restored health state for %d/%d proxies from Redis", loaded, len(self._proxies))

    def _persist_redis(self, entry: ProxyEntry) -> None:
        """Write one proxy's health state to Redis (best-effort, non-blocking)."""
        if not self._redis:
            return
        try:
            r   = self._redis
            key = entry.key
            p   = r.pipeline()
            p.setex(f"sara:proxy:{key}:ema",     _PROXY_KEY_TTL, entry.ema_rate)
            p.setex(f"sara:proxy:{key}:consec",  _PROXY_KEY_TTL, entry.consecutive_fails)
            p.setex(f"sara:proxy:{key}:cooldown",_PROXY_KEY_TTL, entry.cooldown_until)
            p.setex(f"sara:proxy:{key}:latency", _PROXY_KEY_TTL, entry.ema_latency_ms)
            if entry.blocked_domains:
                p.delete(f"sara:proxy:{key}:blocked")
                p.sadd(f"sara:proxy:{key}:blocked", *entry.blocked_domains)
                p.expire(f"sara:proxy:{key}:blocked", _PROXY_KEY_TTL)
            p.execute()
        except Exception as exc:
            logger.debug("ProxyManager: Redis persist failed: %s", exc)

    # ── Proxy selection ────────────────────────────────────────────────────────

    def get_proxy(
        self,
        domain: str,
        tier: ProxyTier = ProxyTier.RESIDENTIAL,
        exclude: Optional[str] = None,
    ) -> Optional[str]:
        """
        Return the best proxy URL for domain.

        Selection algorithm:
          1. Filter: correct tier, not blocked for domain, not the excluded URL
          2. Separate OPEN (weight=0) proxies from candidates
          3. Consistent affinity: pick the highest-weight proxy whose affinity shard
             matches the domain. This gives the same proxy for repeated calls to the
             same domain (good for cookie/session consistency).
          4. If affinity proxy is OPEN or degraded, fall back to weighted random.
          5. Returns None when no proxies are available → direct connection.
        """
        clean_domain = domain.removeprefix("www.")
        with self._lock:
            candidates = [
                p for p in self._proxies
                if p.tier == tier
                and not p.is_blocked_for(clean_domain)
                and p.url != exclude
                and p.weight > 0   # excludes OPEN circuit breaker
            ]
            if not candidates:
                return None

            # Consistent shard for domain affinity
            shard   = int(hashlib.md5(clean_domain.encode()).hexdigest(), 16) % len(candidates)
            primary = candidates[shard]

            if primary.is_healthy and primary.cb_state == CBState.CLOSED:
                primary.total_requests += 1
                return primary.url

            # Primary degraded or half-open — weighted random among all candidates
            weights = [c.weight for c in candidates]
            chosen  = random.choices(candidates, weights=weights, k=1)[0]
            return chosen.url

    def get_proxy_for_request(self, domain: str) -> Optional[str]:
        """Convenience: try residential → datacenter → None (direct)."""
        proxy = self.get_proxy(domain, tier=ProxyTier.RESIDENTIAL)
        if proxy is None:
            proxy = self.get_proxy(domain, tier=ProxyTier.DATACENTER)
        return proxy

    def rotate_and_mark(
        self,
        domain: str,
        failed_url: str,
        blocked: bool = False,
        latency_ms: float = 0.0,
    ) -> Optional[str]:
        """
        Mark failed_url as failed for domain and immediately return the next
        best proxy.  One call instead of report_failure() + get_proxy().

        blocked=True:  proxy got a 403/bot-detected response for this domain.
                       The proxy-domain pair is permanently blacklisted.
        blocked=False: transient error (timeout, connection reset, etc.).
        """
        self.report_failure(domain, failed_url, blocked=blocked)
        return self.get_proxy(domain, exclude=failed_url)

    # ── Feedback ───────────────────────────────────────────────────────────────

    def report_success(
        self,
        domain: str,
        proxy_url: str,
        latency_ms: float = 0.0,
    ) -> None:
        """Record a successful request.  Updates EMA and resets circuit breaker."""
        with self._lock:
            entry = self._find(proxy_url)
            if entry is None:
                return
            prev_state = entry.cb_state
            entry.record_success(latency_ms=latency_ms)
            if prev_state != CBState.CLOSED:
                logger.info(
                    "Proxy %s … circuit CLOSED (recovered for %s, latency=%.0fms)",
                    proxy_url[-30:], domain, latency_ms,
                )
            self._persist_redis(entry)

    def report_failure(
        self,
        domain: str,
        proxy_url: str,
        blocked: bool = False,
    ) -> None:
        """
        Record a failed request.

        blocked=True: marks this proxy as permanently blocked for domain
                      and opens the circuit if threshold is reached.
        """
        with self._lock:
            entry = self._find(proxy_url)
            if entry is None:
                return
            entry.record_failure(domain=domain, blocked=blocked)
            if blocked:
                logger.warning(
                    "Proxy %s … blocked on %s (ema=%.2f)",
                    proxy_url[-30:], domain, entry.ema_rate,
                )
            self._persist_redis(entry)

    def unblock_domain(self, domain: str) -> int:
        """
        Remove domain from ALL proxies' blocked_domains sets.
        Call this when a site changes its bot-detection strategy.
        Returns the number of proxies unblocked.
        """
        clean = domain.removeprefix("www.")
        count = 0
        with self._lock:
            for entry in self._proxies:
                if clean in entry.blocked_domains:
                    entry.blocked_domains.discard(clean)
                    self._persist_redis(entry)
                    count += 1
        if count:
            logger.info("Unblocked domain '%s' on %d proxies", clean, count)
        return count

    def reset_proxy(self, proxy_url: str) -> bool:
        """
        Reset a proxy's health state to factory defaults (full health, no blocks).
        Use after swapping in a fresh proxy IP.
        """
        with self._lock:
            entry = self._find(proxy_url)
            if entry is None:
                return False
            entry.ema_rate          = 1.0
            entry.consecutive_fails = 0
            entry.cooldown_until    = 0.0
            entry.cooldown_mult     = 1
            entry.blocked_domains   = set()
            self._persist_redis(entry)
        logger.info("Reset proxy health: %s …", proxy_url[-30:])
        return True

    # ── Stats & health reporting ───────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            total    = len(self._proxies)
            healthy  = sum(1 for p in self._proxies if p.is_healthy)
            degraded = sum(1 for p in self._proxies if p.cb_state == CBState.CLOSED and p.is_degraded)
            open_cb  = sum(1 for p in self._proxies if p.cb_state == CBState.OPEN)
            half     = sum(1 for p in self._proxies if p.cb_state == CBState.HALF_OPEN)
            avg_ema  = (
                sum(p.ema_rate for p in self._proxies) / total if total else 0.0
            )
            return {
                "total":            total,
                "healthy":          healthy,
                "degraded":         degraded,
                "circuit_open":     open_cb,
                "circuit_half":     half,
                "avg_ema_rate":     round(avg_ema, 3),
            }

    def health_report(self) -> list[dict]:
        """Detailed per-proxy health for the /proxy/health API endpoint."""
        with self._lock:
            return [
                {
                    "url":              p.url[:12] + "…" + p.url[-20:],
                    "tier":             p.tier.value,
                    "cb_state":         p.cb_state.value,
                    "ema_rate":         round(p.ema_rate, 3),
                    "ema_latency_ms":   round(p.ema_latency_ms, 0),
                    "consecutive_fails": p.consecutive_fails,
                    "cooldown_until":   p.cooldown_until,
                    "blocked_domains":  len(p.blocked_domains),
                    "total_requests":   p.total_requests,
                    "total_successes":  p.total_successes,
                    "weight":           round(p.weight, 3),
                }
                for p in self._proxies
            ]

    # ── Private ────────────────────────────────────────────────────────────────

    def _find(self, url: str) -> Optional[ProxyEntry]:
        for p in self._proxies:
            if p.url == url:
                return p
        return None


# ---------------------------------------------------------------------------
# Module-level singleton — shared across all sdfFetch threads in a process
# ---------------------------------------------------------------------------

_manager: Optional[ProxyManager] = None
_manager_lock = Lock()


def get_proxy_manager() -> ProxyManager:
    """Return the process-level ProxyManager singleton, creating it if needed."""
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is not None:
            return _manager
        _manager = ProxyManager.from_env()
    return _manager
