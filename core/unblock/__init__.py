"""
SARA Unblock Layer — transparent anti-bot bypass.

Public API:
    from core.unblock import UnblockFetcher
    fetcher = UnblockFetcher.from_env()
    result  = fetcher.fetch("https://www.myntra.com/...")
    # → {"page_doc": str, "status_code": int, "url": str, "strategy": str}

Strategy escalation (automatic, per-request):
    0  direct        — realistic browser headers, no proxy
    1  proxy         — rotating proxy + realistic headers
    2  cffi          — curl_cffi Chrome TLS fingerprint (bypasses TLS inspection)
    3  cffi+proxy    — curl_cffi + rotating proxy
    4  browser       — Playwright headless (full JS rendering)
    5  browser+proxy — Playwright + proxy (maximum stealth)

Strategies 2–5 require optional extras:
    pip install curl-cffi            # strategies 2–3
    pip install playwright && playwright install chromium   # strategies 4–5
"""
from core.unblock.fetcher import UnblockFetcher, FetchResult

__all__ = ["UnblockFetcher", "FetchResult"]
