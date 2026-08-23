"""
SARA API — Pydantic request/response schemas.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
import re

_SAFE = re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_safe_name(v: str, field_name: str = "value") -> str:
    if not v or not _SAFE.match(v):
        raise ValueError(
            f"{field_name} must contain only letters, digits, underscores, hyphens"
        )
    return v


# ---------------------------------------------------------------------------
# Crawl schemas
# ---------------------------------------------------------------------------

class CrawlTriggerRequest(BaseModel):
    project: str = Field(..., examples=["commerce_crawl"])
    site: str    = Field(..., examples=["myntra_com"])
    schedule_id: str = Field(..., examples=["20260405"])
    use_async_worker: bool = Field(
        False,
        description="If True, launch the async aiohttp worker instead of the legacy sync pipeline",
    )
    priority: int = Field(5, ge=1, le=10, description="Message priority (1=low, 10=high)")

    @field_validator("project")
    @classmethod
    def project_safe(cls, v: str) -> str:
        return _validate_safe_name(v, "project")

    @field_validator("site")
    @classmethod
    def site_safe(cls, v: str) -> str:
        return _validate_safe_name(v, "site")

    @field_validator("schedule_id")
    @classmethod
    def schedule_safe(cls, v: str) -> str:
        return _validate_safe_name(v, "schedule_id")


class CrawlStatus(str, Enum):
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    PENDING   = "pending"


class CrawlRunResponse(BaseModel):
    schedule_id: str
    project: str
    site: str
    status: CrawlStatus
    stage: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    worker_id: Optional[str] = None
    hostname: Optional[str] = None
    progress: Dict[str, Any] = Field(default_factory=dict)


class CrawlListResponse(BaseModel):
    # Multi-server: all active runs across all workers
    current_runs: List[CrawlRunResponse] = Field(default_factory=list)
    # Backward-compat alias — first active run (or None)
    current_run: Optional[CrawlRunResponse] = None
    last_runs: List[CrawlRunResponse] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Worker schemas
# ---------------------------------------------------------------------------

class WorkerInfo(BaseModel):
    worker_key: str           # sara:worker:{hostname}:{worker_id}
    hostname: str
    worker_id: str
    pid: Optional[int] = None
    started_at: Optional[str] = None
    version: Optional[str] = None
    last_seen: Optional[float] = None   # Unix timestamp of last heartbeat
    current_job: Optional[Dict[str, Any]] = None


class WorkerListResponse(BaseModel):
    workers: List[WorkerInfo]
    total: int


# ---------------------------------------------------------------------------
# Site schemas
# ---------------------------------------------------------------------------

class SiteInfo(BaseModel):
    site: str
    project: str
    has_discovery: bool = False
    has_retriever: bool = False
    has_parser: bool = False


class SiteListResponse(BaseModel):
    sites: List[SiteInfo]
    total: int


class CreateSiteRequest(BaseModel):
    project: str
    site: str
    discovery_py: str   = Field(..., description="Python class source for discovery")
    discovery_yml: str  = Field(..., description="YAML depth config for discovery")
    retriever_yml: str  = Field(..., description="YAML request params for retriever")
    parser_py: str      = Field(..., description="Python class source for parser")
    parser_yml: str     = Field(..., description="YAML fields config for parser")

    @field_validator("project")
    @classmethod
    def project_safe(cls, v: str) -> str:
        return _validate_safe_name(v, "project")

    @field_validator("site")
    @classmethod
    def site_safe(cls, v: str) -> str:
        return _validate_safe_name(v, "site")


# ---------------------------------------------------------------------------
# Queue / DLQ schemas
# ---------------------------------------------------------------------------

class QueueDepthResponse(BaseModel):
    queues: Dict[str, int]   # queue_name → message_count
    dlqs: Dict[str, int]     # dlq_name   → message_count
    timestamp: str


class DLQMessage(BaseModel):
    url: str
    domain: Optional[str] = None
    site: Optional[str] = None
    project: Optional[str] = None
    failed_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0
    raw: Dict[str, Any] = Field(default_factory=dict)


class DLQListResponse(BaseModel):
    stage: str
    messages: List[DLQMessage]
    total: int


class DLQRequeueRequest(BaseModel):
    stage: str
    message_ids: List[str] = Field(default_factory=list, description="Empty = requeue all")


# ---------------------------------------------------------------------------
# Proxy / health schemas
# ---------------------------------------------------------------------------

class ProxyHealthResponse(BaseModel):
    total: int
    healthy: int
    degraded: int
    avg_success_rate: float
    entries: List[Dict[str, Any]] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    status: str           # ok | degraded | down
    rabbitmq: str         # ok | error
    redis: str            # ok | error | disabled
    storage: str          # local | s3
    workers_running: int
    uptime_seconds: float
    version: str = "2.0.0"


# ---------------------------------------------------------------------------
# Analytics schemas
# ---------------------------------------------------------------------------

class ThroughputDataPoint(BaseModel):
    timestamp: str
    records_per_second: float
    pages_fetched: int
    errors: int


class AnalyticsSummary(BaseModel):
    total_records_today: int
    total_pages_fetched_today: int
    success_rate_pct: float
    avg_latency_ms: float
    top_sites: List[Dict[str, Any]]
    hourly_throughput: List[ThroughputDataPoint]
