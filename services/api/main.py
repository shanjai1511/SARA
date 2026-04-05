"""
SARA — FastAPI Control Plane.

Provides a REST API for managing and monitoring the SARA crawl pipeline.
Acts as the programmatic interface to SARA — the Streamlit dashboard uses
this under the hood, and external SaaS tenants consume it directly.

Run:
    uvicorn services.api.main:app --host 0.0.0.0 --port 8080 --reload

Endpoints overview:
  /health              — System health check
  /crawls/trigger      — Launch a crawl pipeline
  /crawls/status       — List crawl runs (current + history)
  /crawls/queue/depth  — RabbitMQ queue depths
  /crawls/dlq/{stage}  — Browse and requeue dead-letter messages
  /sites               — CRUD for site configurations
  /proxy/health        — Proxy pool status
  /metrics/summary     — Analytics summary
  /docs                — Auto-generated OpenAPI docs (Swagger UI)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.metrics import start_metrics_server
from core.proxy_manager import ProxyManager
from services.api.routers import crawls, sites
from services.api.schemas import ProxyHealthResponse, SystemHealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sara.api")

_START_TIME = time.time()


# ---------------------------------------------------------------------------
# Auth (Bearer token — simple shared secret for SaaS MVP)
# ---------------------------------------------------------------------------

_security = HTTPBearer(auto_error=False)


def _get_api_key() -> str:
    key = os.environ.get("SARA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("SARA_API_KEY environment variable is not set")
    return key


def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(_security),
) -> str:
    """Validate Bearer token.  Returns the token on success."""
    expected = os.environ.get("SARA_API_KEY", "")
    if not expected:
        # No key configured — allow unauthenticated access (dev mode)
        return "dev"
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    logger.info("SARA API starting up")
    start_metrics_server(port=int(os.environ.get("METRICS_PORT", 8000)))
    yield
    logger.info("SARA API shutting down")


app = FastAPI(
    title="SARA — Scalable Automated Retrieval Architecture",
    description=(
        "Production-grade distributed web crawling platform. "
        "Manage crawl schedules, monitor pipeline health, inspect dead-letter queues, "
        "and configure sites — all via REST API."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — restrict in production via CORS_ORIGINS env var
_cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

app.include_router(crawls.router, dependencies=[Depends(require_auth)])
app.include_router(sites.router,  dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"], summary="System health check")
async def health():
    """
    Returns overall system health: RabbitMQ connectivity, Redis, storage.
    Does NOT require authentication — used by load balancers and k8s probes.
    """
    from config.settings import settings
    from core.broker import get_sync_channel

    rabbitmq_ok = False
    try:
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL, max_attempts=1, base_backoff=1.0)
        conn.close()
        rabbitmq_ok = True
    except Exception:
        pass

    redis_status = "disabled"
    redis_url = getattr(settings, "REDIS_URL", None)
    if redis_url:
        try:
            import redis as _redis
            r = _redis.from_url(redis_url, socket_timeout=2)
            r.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "error"

    from core.storage import get_storage
    store = get_storage(base_dir=ROOT / "scrape_output" / "raw_html")
    storage_type = "s3" if "S3Storage" in type(store).__name__ else "local"

    overall = "ok" if rabbitmq_ok else "degraded"

    return SystemHealthResponse(
        status=overall,
        rabbitmq="ok" if rabbitmq_ok else "error",
        redis=redis_status,
        storage=storage_type,
        workers_running=0,   # TODO: query k8s/docker for running pods
        uptime_seconds=round(time.time() - _START_TIME, 1),
    )


@app.get("/proxy/health", tags=["System"], response_model=ProxyHealthResponse,
         summary="Proxy pool health")
async def proxy_health(_: str = Depends(require_auth)):
    """Return health stats for the proxy pool."""
    mgr = ProxyManager.from_env()
    stats = mgr.stats()
    report = mgr.health_report()
    return ProxyHealthResponse(
        total=stats["total"],
        healthy=stats["healthy"],
        degraded=stats["degraded"],
        avg_success_rate=round(stats["avg_success_rate"], 3),
        entries=report,
    )


@app.get("/metrics/summary", tags=["Analytics"], summary="Analytics summary")
async def metrics_summary(_: str = Depends(require_auth)):
    """
    Aggregate crawl stats from crawl_status.json.
    For rich time-series analytics, connect Grafana to Prometheus directly.
    """
    from sdf_module.crawl_status import get_status
    data = get_status()
    last_runs = data.get("last_runs", [])

    total_records = sum(
        r.get("progress", {}).get("parser_records", 0) for r in last_runs
    )
    total_pages = sum(
        r.get("progress", {}).get("retriever_fetched", 0) for r in last_runs
    )
    completed = sum(1 for r in last_runs if r.get("status") == "completed")
    success_rate = (completed / len(last_runs) * 100) if last_runs else 0.0

    # Top sites by record count
    site_records: dict[str, int] = {}
    for r in last_runs:
        key = f"{r.get('site', '?')}/{r.get('project', '?')}"
        site_records[key] = site_records.get(key, 0) + r.get("progress", {}).get("parser_records", 0)
    top_sites = sorted(
        [{"site": k, "records": v} for k, v in site_records.items()],
        key=lambda x: x["records"],
        reverse=True,
    )[:10]

    return {
        "total_records_all_time": total_records,
        "total_pages_all_time": total_pages,
        "total_runs": len(last_runs),
        "success_rate_pct": round(success_rate, 1),
        "top_sites": top_sites,
        "current_run": data.get("current_run"),
    }


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
