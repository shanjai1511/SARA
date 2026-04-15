"""
SARA Unblock Service — HTTP API for anti-bot page fetching.

A drop-in alternative to Zyte API / ScraperAPI / BrightData Scraping Browser.
Accepts a URL + options, runs the appropriate strategy, and returns the HTML.

Run standalone:
    uvicorn services.unblock.main:app --host 0.0.0.0 --port 8888 --workers 4

Or via Docker:
    docker-compose up -d sara-unblock

Endpoints:
    POST /fetch                — Fetch a URL (main API)
    GET  /fetch/batch          — Fetch multiple URLs in parallel
    GET  /health               — Service health + strategy availability
    GET  /domains              — Domain strategy registry (which strategy works per domain)
    DELETE /domains/{domain}   — Reset domain strategy (force re-probe from strategy 0)
    GET  /metrics              — Prometheus metrics

Compatible with the Zyte API request format (subset):
    POST /fetch
    {
      "url": "https://www.myntra.com/...",
      "browserHtml": true,            // force Playwright (strategy ≥ 4)
      "httpResponseBody": true,       // plain HTTP only (strategy ≤ 1)
      "geolocation": "IN",            // not yet implemented (future)
    }

SARA-native request format:
    POST /fetch
    {
      "url": "https://www.myntra.com/...",
      "strategy": 0,                  // start at this strategy (default: auto)
      "max_strategy": 5,              // override max strategy for this request
      "referer": "https://...",       // optional Referer header
      "proxy": "http://user:pass@...", // override proxy for this request
    }
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from core.unblock import UnblockFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [unblock] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sara.unblock")

# ---------------------------------------------------------------------------
# Global fetcher instance (shared across all requests — thread-safe)
# ---------------------------------------------------------------------------

_fetcher: Optional[UnblockFetcher] = None


def get_fetcher() -> UnblockFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = UnblockFetcher.from_env()
    return _fetcher


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class FetchRequest(BaseModel):
    url: str = Field(..., description="URL to fetch")

    # Strategy control
    strategy:     int  = Field(0,  ge=0, le=5,  description="Minimum strategy index to start from (0=auto)")
    max_strategy: int  = Field(5,  ge=0, le=5,  description="Maximum strategy index to attempt")

    # Request hints
    referer: Optional[str] = Field(None, description="Referer header to send")
    proxy:   Optional[str] = Field(None, description="Override proxy URL (http://user:pass@host:port)")

    # Zyte API compatibility flags
    browserHtml:      bool = Field(False, description="Force Playwright rendering (equivalent to strategy≥4)")
    httpResponseBody: bool = Field(False, description="Prefer plain HTTP (strategy≤1, no browser)")

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class BatchFetchRequest(BaseModel):
    urls:         List[str] = Field(..., min_length=1, max_length=50)
    strategy:     int = Field(0, ge=0, le=5)
    max_strategy: int = Field(5, ge=0, le=5)
    referer:      Optional[str] = None


class FetchResponse(BaseModel):
    url:         str
    final_url:   str
    status_code: Optional[int]
    page_doc:    str
    strategy:    str
    elapsed:     float
    ok:          bool


class HealthResponse(BaseModel):
    status:           str
    strategies:       dict
    proxy_count:      int
    domains_tracked:  int
    uptime_seconds:   float
    version:          str = "1.0.0"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_START = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SARA Unblock Service starting…")
    # Warm up fetcher (initialises optional deps, checks proxies)
    get_fetcher()
    yield
    logger.info("SARA Unblock Service shutting down")


app = FastAPI(
    title="SARA Unblock Service",
    description=(
        "Anti-bot HTTP fetching service. "
        "Automatically escalates through increasingly powerful strategies "
        "(plain HTTP → proxy → TLS impersonation → headless browser) "
        "until the page is successfully retrieved. "
        "Drop-in alternative to Zyte API / ScraperAPI."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth (optional — shared secret via SARA_UNBLOCK_API_KEY)
# ---------------------------------------------------------------------------

def _check_auth(request: Request) -> None:
    key = os.environ.get("SARA_UNBLOCK_API_KEY", "").strip()
    if not key:
        return   # no key configured — open access (dev mode)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# /fetch
# ---------------------------------------------------------------------------

@app.post("/fetch", response_model=FetchResponse, summary="Fetch a URL")
async def fetch_url(req: FetchRequest, request: Request):
    """
    Fetch a URL using the configured strategy escalation.

    **Automatic mode** (strategy=0, max_strategy=5):
      The service remembers which strategy worked last time for each domain
      and starts from there — no wasted retries.

    **Force browser** (browserHtml=true):
      Equivalent to setting strategy=4. Use for JS-heavy SPAs (Myntra, Meesho, etc.)

    **Force plain HTTP** (httpResponseBody=true):
      Equivalent to setting max_strategy=1. Use for simple sites to save resources.
    """
    _check_auth(request)

    fetcher = get_fetcher()

    start_strategy = req.strategy
    max_strategy   = req.max_strategy

    # Zyte API compat overrides
    if req.browserHtml:
        start_strategy = max(start_strategy, 4)
    if req.httpResponseBody:
        max_strategy = min(max_strategy, 1)

    # Apply max_strategy cap for this request
    orig_max = fetcher._max_strategy
    fetcher._max_strategy = max_strategy

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fetcher.fetch(req.url, start_strategy=start_strategy, referer=req.referer),
        )
    finally:
        fetcher._max_strategy = orig_max

    return FetchResponse(
        url=req.url,
        final_url=result.url,
        status_code=result.status_code,
        page_doc=result.page_doc,
        strategy=result.strategy,
        elapsed=round(result.elapsed, 3),
        ok=result.ok,
    )


# ---------------------------------------------------------------------------
# /fetch/batch
# ---------------------------------------------------------------------------

@app.post("/fetch/batch", summary="Fetch multiple URLs in parallel")
async def fetch_batch(req: BatchFetchRequest, request: Request):
    """
    Fetch up to 50 URLs in parallel (one thread per URL).
    Each URL is fetched independently with its own strategy escalation.
    Results are returned in the same order as the input URLs.
    """
    _check_auth(request)
    fetcher = get_fetcher()

    loop = asyncio.get_event_loop()

    async def _one(url: str):
        return await loop.run_in_executor(
            None,
            lambda: fetcher.fetch(url, start_strategy=req.strategy, referer=req.referer),
        )

    results = await asyncio.gather(*[_one(u) for u in req.urls], return_exceptions=True)

    items = []
    for url, r in zip(req.urls, results):
        if isinstance(r, Exception):
            items.append({
                "url": url, "ok": False, "error": str(r),
                "status_code": None, "page_doc": "", "strategy": "error",
            })
        else:
            items.append({
                "url":         url,
                "final_url":   r.url,
                "ok":          r.ok,
                "status_code": r.status_code,
                "page_doc":    r.page_doc,
                "strategy":    r.strategy,
                "elapsed":     round(r.elapsed, 3),
            })

    return {"results": items, "total": len(items)}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, summary="Service health")
async def health():
    """Service health — available strategies, proxy count, tracked domains."""
    fetcher = get_fetcher()
    return HealthResponse(
        status="ok",
        strategies={
            "direct":         True,
            "proxy":          bool(fetcher._proxies),
            "cffi":           fetcher._cffi_available,
            "cffi+proxy":     fetcher._cffi_available and bool(fetcher._proxies),
            "browser":        fetcher._browser_available,
            "browser+proxy":  fetcher._browser_available and bool(fetcher._proxies),
        },
        proxy_count=len(fetcher._proxies),
        domains_tracked=len(fetcher._domain_configs),
        uptime_seconds=round(time.time() - _START, 1),
    )


# ---------------------------------------------------------------------------
# /domains — strategy registry
# ---------------------------------------------------------------------------

@app.get("/domains", summary="Domain strategy registry")
async def list_domains():
    """
    Return all domains the service has learned about, with their recorded
    minimum working strategy and last successful fetch time.
    """
    fetcher = get_fetcher()
    with fetcher._lock:
        entries = [
            {
                "domain":       domain,
                "min_strategy": cfg.min_strategy,
                "strategy_name": fetcher.STRATEGY_NAMES[cfg.min_strategy],
                "last_success": cfg.last_success,
            }
            for domain, cfg in fetcher._domain_configs.items()
        ]
    entries.sort(key=lambda x: x["min_strategy"], reverse=True)
    return {"domains": entries, "total": len(entries)}


@app.delete("/domains/{domain}", summary="Reset domain strategy")
async def reset_domain(domain: str, request: Request):
    """
    Clear the cached strategy for a domain, forcing the service to re-probe
    from strategy 0 on the next request.  Use when a site's anti-bot changes.
    """
    _check_auth(request)
    fetcher = get_fetcher()
    with fetcher._lock:
        removed = fetcher._domain_configs.pop(domain, None)
    if removed:
        return {"reset": True, "domain": domain}
    raise HTTPException(status_code=404, detail=f"Domain '{domain}' not found in registry")


# ---------------------------------------------------------------------------
# /metrics (Prometheus text format)
# ---------------------------------------------------------------------------

@app.get("/metrics", summary="Prometheus metrics")
async def prometheus_metrics():
    """Expose basic counters in Prometheus text format."""
    fetcher = get_fetcher()
    with fetcher._lock:
        domain_count = len(fetcher._domain_configs)
        strategy_dist: dict[int, int] = {}
        for cfg in fetcher._domain_configs.values():
            strategy_dist[cfg.min_strategy] = strategy_dist.get(cfg.min_strategy, 0) + 1

    lines = [
        "# HELP sara_unblock_domains_tracked Number of domains with a known strategy",
        "# TYPE sara_unblock_domains_tracked gauge",
        f"sara_unblock_domains_tracked {domain_count}",
        "# HELP sara_unblock_proxy_count Number of configured proxies",
        "# TYPE sara_unblock_proxy_count gauge",
        f"sara_unblock_proxy_count {len(fetcher._proxies)}",
        "# HELP sara_unblock_uptime_seconds Service uptime in seconds",
        "# TYPE sara_unblock_uptime_seconds counter",
        f"sara_unblock_uptime_seconds {round(time.time() - _START, 1)}",
    ]
    for idx, count in sorted(strategy_dist.items()):
        name = UnblockFetcher.STRATEGY_NAMES[idx]
        lines.append(
            f'sara_unblock_domain_strategy_count{{strategy="{name}"}} {count}'
        )

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Generic exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def _generic(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "services.unblock.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("UNBLOCK_PORT", 8888)),
        workers=int(os.environ.get("UNBLOCK_WORKERS", 2)),
        log_level="info",
    )
