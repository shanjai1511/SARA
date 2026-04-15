"""
SARA — Playwright sync browser pool for JS rendering.

Manages a fixed-size pool of persistent browser contexts.
Each `acquire()` call returns an isolated page; the context is
closed and recycled after the request (memory isolation between sites).

Requirements:
    pip install playwright
    playwright install chromium

Graceful degradation:
    If playwright is not installed, `BrowserPool` raises `ImportError` at
    construction time.  `UnblockFetcher` catches this and skips browser strategies.

Thread safety:
    The pool uses a threading.Semaphore to cap concurrency.
    Playwright's sync API is not thread-safe for shared Browser objects, so
    each slot owns an independent BrowserContext (separate cookie jar, cache).
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",   # hides navigator.webdriver
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-gpu",
    "--window-size=1920,1080",
]

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
window.chrome = {runtime: {}};
""".strip()


class BrowserPool:
    """
    Fixed-size pool of Playwright browser contexts.

    Usage:
        pool = BrowserPool(size=3)
        with pool.acquire() as page:
            page.goto(url)
            html = page.content()
    """

    def __init__(self, size: int = 2, headless: bool = True):
        from playwright.sync_api import sync_playwright  # type: ignore

        self._size     = size
        self._headless = headless
        self._lock     = threading.Lock()
        self._sem      = threading.Semaphore(size)
        self._pw       = sync_playwright().start()
        self._browser  = self._pw.chromium.launch(
            headless=headless,
            args=_LAUNCH_ARGS,
        )
        logger.info("BrowserPool started: size=%d headless=%s", size, headless)

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    @contextmanager
    def acquire(
        self,
        proxy_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        timeout_ms: int = 30_000,
    ) -> Generator:
        """
        Context manager yielding a fresh Playwright Page.

        The browser context (cookies, cache, storage) is created fresh for
        each acquisition and closed on exit — full isolation between sites.
        """
        self._sem.acquire()
        ctx = page = None
        try:
            ctx_opts: dict = {
                "viewport":        {"width": 1920, "height": 1080},
                "java_script_enabled": True,
                "accept_downloads": False,
                "ignore_https_errors": True,
            }
            if user_agent:
                ctx_opts["user_agent"] = user_agent
            if proxy_url:
                # Playwright proxy format: {"server": "http://host:port", ...}
                ctx_opts["proxy"] = _parse_proxy(proxy_url)

            ctx  = self._browser.new_context(**ctx_opts)
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)

            # Inject stealth script on every new page
            ctx.add_init_script(_STEALTH_SCRIPT)

            yield page

        finally:
            # Always clean up context — prevents cookie/cache leakage
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass
            self._sem.release()


def _parse_proxy(proxy_url: str) -> dict:
    """
    Convert http://user:pass@host:port → Playwright proxy dict.
    """
    from urllib.parse import urlparse
    p = urlparse(proxy_url)
    result: dict = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        result["username"] = p.username
    if p.password:
        result["password"] = p.password
    return result


def render_page(
    pool: BrowserPool,
    url: str,
    proxy_url: Optional[str] = None,
    user_agent: Optional[str] = None,
    wait_for: str = "domcontentloaded",
    extra_wait_ms: int = 0,
    timeout_ms: int = 30_000,
) -> dict:
    """
    Render a URL with the browser pool and return the page HTML.

    Returns:
        {
            "page_doc":    str,   # rendered HTML (after JS execution)
            "status_code": int,   # HTTP status code of the navigation
            "url":         str,   # final URL after redirects
            "strategy":    str,   # "browser" or "browser+proxy"
        }
    """
    strategy = "browser+proxy" if proxy_url else "browser"
    start = time.time()

    try:
        with pool.acquire(proxy_url=proxy_url, user_agent=user_agent, timeout_ms=timeout_ms) as page:
            # Capture HTTP response status
            _status_holder: list[int] = []

            def _on_response(response):
                if response.url == page.url or not _status_holder:
                    _status_holder.append(response.status)

            page.on("response", _on_response)

            response = page.goto(url, wait_until=wait_for, timeout=timeout_ms)
            status   = response.status if response else 0

            if extra_wait_ms > 0:
                page.wait_for_timeout(extra_wait_ms)

            html = page.content()
            final_url = page.url

            elapsed = time.time() - start
            logger.debug(
                "Browser render: %s  status=%d  strategy=%s  elapsed=%.2fs",
                url, status, strategy, elapsed,
            )

            return {
                "page_doc":    html,
                "status_code": status,
                "url":         final_url,
                "strategy":    strategy,
            }

    except Exception as exc:
        logger.warning("Browser render failed: %s  error=%s", url, exc)
        return {
            "page_doc":    "",
            "status_code": None,
            "url":         url,
            "strategy":    strategy,
        }


# Module-level singleton (lazy — only created on first use)
_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def get_pool(size: int = 2) -> Optional[BrowserPool]:
    """Return the module-level BrowserPool, creating it on first call."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        try:
            _pool = BrowserPool(size=size)
            return _pool
        except Exception as exc:
            logger.warning("BrowserPool unavailable: %s", exc)
            return None
