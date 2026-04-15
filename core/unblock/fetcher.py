"""
SARA UnblockFetcher — multi-strategy escalating HTTP fetcher.

Escalation order (cheapest → most expensive):
  0  direct          plain requests + realistic browser fingerprint
  1  proxy           rotating proxy + realistic browser fingerprint
  2  cffi            curl_cffi Chrome TLS impersonation (bypasses TLS fingerprinting)
  3  cffi+proxy      curl_cffi + rotating proxy
  4  browser         Playwright headless (JS rendering, full browser stack)
  5  browser+proxy   Playwright + proxy (maximum stealth)

For each strategy, if the response is a block signal (403, 429, empty body
behind a bot check) we immediately escalate to the next strategy.  On a
successful 200 the result is returned and no further strategies are tried.

Domain-level strategy floor:
    Some sites are known to require a minimum strategy level (e.g. Myntra
    always needs at least strategy 3).  These are tracked in `domain_config`
    and written back as feedback when a higher strategy succeeds for the first
    time.

Thread safety:
    UnblockFetcher is fully thread-safe.  Proxy selection and domain config
    updates are protected by a threading.Lock.

Optional dependencies:
    curl_cffi:  pip install curl-cffi      (strategies 2–3)
    playwright: pip install playwright && playwright install chromium  (4–5)
    Both fall back gracefully if not installed.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    page_doc:    str
    status_code: Optional[int]
    url:         str
    strategy:    str
    elapsed:     float = 0.0

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and bool(self.page_doc.strip())

    def to_dict(self) -> dict:
        return {
            "page_doc":    self.page_doc,
            "status_code": self.status_code,
            "url":         self.url,
            "strategy":    self.strategy,
        }


# ---------------------------------------------------------------------------
# Block-signal detection
# ---------------------------------------------------------------------------

_BLOCK_STATUSES = {403, 407, 429, 503}

# Strings found in page body that indicate a bot-challenge page (not real content)
_BLOCK_BODY_SIGNALS = [
    "Access Denied",
    "403 Forbidden",
    "blocked",
    "Please verify you are a human",
    "Checking your browser",
    "Just a moment",        # Cloudflare
    "cf-browser-verification",
    "ddos-guard",
    "perimeterx",
    "DataDome",
    "Enable JavaScript and cookies to continue",
    "Please enable cookies",
    "Ray ID",               # Cloudflare error pages
    "captcha",
    "CAPTCHA",
]

_MIN_BODY_LENGTH = 500   # bodies shorter than this are likely bot challenges


def _is_blocked(result: FetchResult) -> bool:
    """Return True if this response looks like a block/challenge page."""
    if result.status_code in _BLOCK_STATUSES:
        return True
    if result.status_code == 200:
        body = result.page_doc
        # Too short to be real content
        if len(body.strip()) < _MIN_BODY_LENGTH:
            return True
        # Known challenge page fingerprints
        body_lower = body.lower()
        if any(sig.lower() in body_lower for sig in _BLOCK_BODY_SIGNALS):
            return True
    return False


# ---------------------------------------------------------------------------
# Domain config  — remembers the minimum working strategy per domain
# ---------------------------------------------------------------------------

@dataclass
class DomainConfig:
    min_strategy: int = 0        # lowest strategy that has ever worked
    last_success: float = 0.0    # Unix timestamp of last successful fetch
    extra_wait_ms: int = 0       # extra browser wait after page load (for SPAs)


# ---------------------------------------------------------------------------
# UnblockFetcher
# ---------------------------------------------------------------------------

class UnblockFetcher:
    """
    Multi-strategy fetcher.  Escalates through increasingly powerful approaches
    until the page is successfully retrieved or all strategies are exhausted.
    """

    STRATEGY_NAMES = [
        "direct",
        "proxy",
        "cffi",
        "cffi+proxy",
        "browser",
        "browser+proxy",
    ]

    def __init__(
        self,
        proxy_list: list[list] | None = None,
        max_strategy: int = 5,
        browser_pool_size: int = 2,
        timeout: int = 30,
        proxy_manager=None,   # optional pre-built ProxyManager instance
    ):
        """
        proxy_list:       [[host, port, user, pass], ...] — same format as WEBSHARE_PROXY_JSON
        max_strategy:     highest strategy index to attempt (0–5)
        browser_pool_size: number of concurrent Playwright browsers
        timeout:          per-request timeout in seconds
        proxy_manager:    pre-built ProxyManager (shares health state with sdfFetch)
        """
        self._lock = threading.Lock()
        self._domain_configs: Dict[str, DomainConfig] = {}
        self._max_strategy  = max_strategy
        self._timeout       = timeout
        self._browser_size  = browser_pool_size
        self._browser_pool  = None   # lazy — created on first browser strategy

        # Use an injected ProxyManager if provided, otherwise build from proxy_list
        if proxy_manager is not None:
            self._proxy_mgr = proxy_manager
        elif proxy_list:
            from core.proxy_manager import ProxyManager
            self._proxy_mgr = ProxyManager.from_list(proxy_list)
        else:
            self._proxy_mgr = None

        # Expose raw list for compatibility checks
        self._proxies: list[str] = (
            [p.url for p in self._proxy_mgr._proxies]
            if self._proxy_mgr and self._proxy_mgr._proxies
            else []
        )

        if not self._proxies:
            logger.info("UnblockFetcher: no proxies configured — max strategy capped at 1")
            self._max_strategy = min(max_strategy, 1)
        else:
            logger.info("UnblockFetcher: loaded %d proxies via ProxyManager", len(self._proxies))

        # Check optional dependencies
        self._cffi_available     = self._check_cffi()
        self._browser_available  = self._check_playwright()

        effective_max = self._max_strategy
        if not self._cffi_available:
            effective_max = min(effective_max, 1)  # skip cffi strategies
            if self._browser_available:
                effective_max = max_strategy       # but allow browser ones
        if not self._browser_available:
            effective_max = min(effective_max, 3 if self._cffi_available else 1)

        logger.info(
            "UnblockFetcher ready: max_strategy=%d cffi=%s browser=%s proxies=%d",
            effective_max,
            self._cffi_available,
            self._browser_available,
            len(self._proxies),
        )

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, max_strategy: int = 5) -> "UnblockFetcher":
        """Build from env vars, sharing the process-level ProxyManager singleton."""
        from core.proxy_manager import get_proxy_manager
        max_strat = int(os.environ.get("SARA_UNBLOCK_MAX_STRATEGY", str(max_strategy)))
        mgr = get_proxy_manager()
        return cls(proxy_manager=mgr, max_strategy=max_strat)

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(
        self,
        url: str,
        start_strategy: int = 0,
        referer: Optional[str] = None,
    ) -> FetchResult:
        """
        Fetch url using escalating strategies.  Starts at max(start_strategy,
        domain_floor) and escalates until success or max_strategy exhausted.
        """
        domain = self._domain(url)
        with self._lock:
            cfg = self._domain_configs.setdefault(domain, DomainConfig())
            floor = cfg.min_strategy

        start = max(start_strategy, floor)

        for strategy_idx in range(start, self._max_strategy + 1):
            name = self.STRATEGY_NAMES[strategy_idx]

            # Skip unavailable strategies
            if strategy_idx in (2, 3) and not self._cffi_available:
                continue
            if strategy_idx in (4, 5) and not self._browser_available:
                continue
            if strategy_idx in (1, 3, 5) and not self._proxies:
                continue

            logger.debug("UnblockFetcher: trying strategy=%s for %s", name, url)
            t0 = time.time()
            result = self._run_strategy(strategy_idx, url, domain, referer)
            result.elapsed = time.time() - t0

            # Determine which proxy was used (for feedback)
            _used_proxy = (
                self._pick_proxy(domain) if strategy_idx in (1, 3, 5) else None
            )

            if result.ok:
                # Feed success back to ProxyManager
                if _used_proxy:
                    self._report_proxy_success(domain, _used_proxy, latency_ms=result.elapsed * 1000)

                # Record the floor for this domain if this strategy is higher than known floor
                with self._lock:
                    cfg = self._domain_configs.setdefault(domain, DomainConfig())
                    if strategy_idx > cfg.min_strategy:
                        cfg.min_strategy = strategy_idx
                        logger.info(
                            "Domain %s: raised min_strategy to %d (%s)",
                            domain, strategy_idx, name,
                        )
                    cfg.last_success = time.time()

                logger.info(
                    "UnblockFetcher: SUCCESS strategy=%s status=%d elapsed=%.2fs url=%s",
                    name, result.status_code, result.elapsed, url,
                )
                return result

            # Feed failure back to ProxyManager
            if _used_proxy:
                blocked = result.status_code in (403, 407)
                self._report_proxy_failure(domain, _used_proxy, blocked=blocked)

            logger.debug(
                "UnblockFetcher: strategy=%s BLOCKED status=%s — escalating",
                name, result.status_code,
            )

        # All strategies exhausted
        logger.warning("UnblockFetcher: all strategies failed for %s", url)
        return FetchResult(page_doc="", status_code=None, url=url, strategy="exhausted")

    def get_domain_strategy(self, domain: str) -> int:
        """Return the recorded minimum working strategy for a domain (0 if unknown)."""
        with self._lock:
            return self._domain_configs.get(domain, DomainConfig()).min_strategy

    # ── Strategy implementations ──────────────────────────────────────────────

    def _run_strategy(
        self,
        idx: int,
        url: str,
        domain: str,
        referer: Optional[str],
    ) -> FetchResult:
        name = self.STRATEGY_NAMES[idx]
        try:
            if idx == 0:
                return self._direct(url, domain, referer)
            if idx == 1:
                return self._proxy(url, domain, referer)
            if idx == 2:
                return self._cffi(url, domain, referer, proxy=None)
            if idx == 3:
                return self._cffi(url, domain, referer, proxy=self._pick_proxy(domain))
            if idx == 4:
                return self._browser_fetch(url, domain, proxy=None)
            if idx == 5:
                return self._browser_fetch(url, domain, proxy=self._pick_proxy(domain))
        except Exception as exc:
            logger.debug("Strategy %s exception for %s: %s", name, url, exc)
        return FetchResult(page_doc="", status_code=None, url=url, strategy=name)

    # ── Strategy 0: direct + fingerprint ──────────────────────────────────────

    def _direct(self, url: str, domain: str, referer: Optional[str]) -> FetchResult:
        from core.unblock.fingerprint import get_profile_for_domain
        import requests
        profile  = get_profile_for_domain(domain)
        headers  = profile.to_headers(referer=referer)
        session  = requests.Session()
        response = session.get(url, headers=headers, timeout=self._timeout, verify=True)
        result   = FetchResult(
            page_doc=response.text,
            status_code=response.status_code,
            url=response.url,
            strategy="direct",
        )
        if _is_blocked(result):
            return result
        return result

    # ── Strategy 1: proxy + fingerprint ───────────────────────────────────────

    def _proxy(self, url: str, domain: str, referer: Optional[str]) -> FetchResult:
        from core.unblock.fingerprint import rotate_profile
        import requests
        proxy_url = self._pick_proxy(domain)
        if not proxy_url:
            return FetchResult(page_doc="", status_code=None, url=url, strategy="proxy")
        profile  = rotate_profile()
        headers  = profile.to_headers(referer=referer)
        session  = requests.Session()
        proxies  = {"http": proxy_url, "https": proxy_url}
        response = session.get(url, headers=headers, proxies=proxies, timeout=self._timeout, verify=True)
        return FetchResult(
            page_doc=response.text,
            status_code=response.status_code,
            url=response.url,
            strategy="proxy",
        )

    # ── Strategies 2–3: curl_cffi (Chrome TLS impersonation) ─────────────────

    def _cffi(
        self,
        url: str,
        domain: str,
        referer: Optional[str],
        proxy: Optional[str],
    ) -> FetchResult:
        from curl_cffi import requests as cffi_requests  # type: ignore
        from core.unblock.fingerprint import get_profile_for_domain, rotate_profile

        profile    = rotate_profile() if proxy else get_profile_for_domain(domain)
        impersonate = profile.impersonate or "chrome124"
        headers    = profile.to_headers(referer=referer)
        headers.pop("Accept-Encoding", None)   # curl_cffi manages this

        kwargs: dict = {
            "headers":     headers,
            "timeout":     self._timeout,
            "impersonate": impersonate,
            "verify":      False,              # cffi handles TLS internally
        }
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}

        response = cffi_requests.get(url, **kwargs)
        strategy = "cffi+proxy" if proxy else "cffi"
        return FetchResult(
            page_doc=response.text,
            status_code=response.status_code,
            url=str(response.url),
            strategy=strategy,
        )

    # ── Strategies 4–5: Playwright headless browser ───────────────────────────

    def _browser_fetch(
        self,
        url: str,
        domain: str,
        proxy: Optional[str],
    ) -> FetchResult:
        from core.unblock.browser import get_pool, render_page
        from core.unblock.fingerprint import get_profile_for_domain

        pool = self._get_browser_pool()
        if pool is None:
            return FetchResult(page_doc="", status_code=None, url=url, strategy="browser")

        profile = get_profile_for_domain(domain)
        with self._lock:
            cfg = self._domain_configs.get(domain, DomainConfig())
            extra_wait = cfg.extra_wait_ms

        result_dict = render_page(
            pool=pool,
            url=url,
            proxy_url=proxy,
            user_agent=profile.user_agent,
            extra_wait_ms=extra_wait,
            timeout_ms=self._timeout * 1000,
        )
        return FetchResult(**result_dict, elapsed=0.0)

    # ── Browser pool (lazy init) ───────────────────────────────────────────────

    def _get_browser_pool(self):
        if self._browser_pool is not None:
            return self._browser_pool
        with self._lock:
            if self._browser_pool is not None:
                return self._browser_pool
            try:
                from core.unblock.browser import BrowserPool
                self._browser_pool = BrowserPool(size=self._browser_size)
            except Exception as exc:
                logger.warning("Cannot create BrowserPool: %s", exc)
                self._browser_pool = None
        return self._browser_pool

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.removeprefix("www.") or url

    def _pick_proxy(self, domain: str, exclude: Optional[str] = None) -> Optional[str]:
        """Return the best proxy for domain via ProxyManager (health-aware)."""
        if self._proxy_mgr:
            return self._proxy_mgr.get_proxy_for_request(domain) if not exclude \
                else self._proxy_mgr.get_proxy(domain, exclude=exclude)
        # Fallback: raw list without health tracking
        if not self._proxies:
            return None
        candidates = [p for p in self._proxies if p != exclude]
        if not candidates:
            return None
        idx = int(hashlib.md5(domain.encode()).hexdigest(), 16) % len(candidates)
        return candidates[idx]

    def _report_proxy_success(self, domain: str, proxy_url: str, latency_ms: float = 0.0) -> None:
        if self._proxy_mgr and proxy_url:
            self._proxy_mgr.report_success(domain, proxy_url, latency_ms=latency_ms)

    def _report_proxy_failure(self, domain: str, proxy_url: str, blocked: bool = False) -> None:
        if self._proxy_mgr and proxy_url:
            self._proxy_mgr.report_failure(domain, proxy_url, blocked=blocked)

    @staticmethod
    def _check_cffi() -> bool:
        try:
            import curl_cffi  # type: ignore  # noqa: F401
            return True
        except ImportError:
            logger.info("curl_cffi not installed — TLS impersonation strategies disabled")
            return False

    @staticmethod
    def _check_playwright() -> bool:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore  # noqa: F401
            return True
        except ImportError:
            logger.info("playwright not installed — browser strategies disabled")
            return False
