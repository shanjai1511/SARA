"""
SARA API — Crawl management endpoints.

POST /crawls/trigger          — Launch a crawl pipeline
GET  /crawls/status           — Current + recent run status
GET  /crawls/{schedule_id}    — Status for a specific run
GET  /crawls/queue/depth      — RabbitMQ queue depths
GET  /crawls/dlq/{stage}      — Browse dead-letter queue
POST /crawls/dlq/{stage}/requeue — Requeue DLQ messages
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent.parent.parent

sys.path.insert(0, str(ROOT))

from services.api.schemas import (
    CrawlListResponse,
    CrawlRunResponse,
    CrawlStatus,
    CrawlTriggerRequest,
    DLQListResponse,
    DLQMessage,
    QueueDepthResponse,
)
from sdf_module.crawl_status import get_status

logger = logging.getLogger("sara.api.crawls")
router = APIRouter(prefix="/crawls", tags=["Crawls"])


# ---------------------------------------------------------------------------
# Background crawl launcher
# ---------------------------------------------------------------------------

_running_pids: dict[str, int] = {}   # schedule_id → PID


def _launch_crawl(req: CrawlTriggerRequest) -> int:
    """Launch crawl_runner.py in a subprocess. Return PID."""
    if req.use_async_worker:
        # Launch async discovery + retriever workers
        cmd = [
            sys.executable, "-m", "services.discovery.worker",
            "--project", req.project,
            "--site", req.site,
            "--schedule", req.schedule_id,
        ]
    else:
        cmd = [
            sys.executable, str(ROOT / "crawl_runner.py"),
            req.project, req.site, req.schedule_id,
        ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/trigger", summary="Launch a crawl pipeline")
async def trigger_crawl(
    req: CrawlTriggerRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger a crawl for a project/site/schedule combination.
    The pipeline runs asynchronously in a subprocess.
    """
    key = f"{req.project}_{req.site}_{req.schedule_id}"
    if key in _running_pids:
        raise HTTPException(
            status_code=409,
            detail=f"Crawl already running for schedule_id={req.schedule_id}",
        )

    def _run():
        pid = _launch_crawl(req)
        _running_pids[key] = pid
        logger.info(
            "Crawl launched: project=%s site=%s schedule=%s pid=%d",
            req.project, req.site, req.schedule_id, pid,
        )

    background_tasks.add_task(_run)
    return {
        "message": "Crawl triggered",
        "project": req.project,
        "site": req.site,
        "schedule_id": req.schedule_id,
        "mode": "async" if req.use_async_worker else "sync",
    }


@router.get("/status", response_model=CrawlListResponse, summary="List crawl runs")
async def list_crawls(
    project: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Return current run and recent history, with optional project/site filter."""
    data = get_status()
    current = data.get("current_run")
    last_runs = data.get("last_runs", [])

    def _run_to_schema(r: dict) -> CrawlRunResponse:
        status_str = r.get("status", "running")
        status = (
            CrawlStatus.COMPLETED if status_str == "completed"
            else CrawlStatus.FAILED if status_str == "failed"
            else CrawlStatus.RUNNING
        )
        return CrawlRunResponse(
            schedule_id=r.get("schedule_id", ""),
            project=r.get("project", ""),
            site=r.get("site", ""),
            status=status,
            stage=r.get("stage"),
            started_at=r.get("started_at"),
            completed_at=r.get("completed_at"),
            progress=r.get("progress", {}),
        )

    # Apply filters
    if project:
        last_runs = [r for r in last_runs if r.get("project") == project]
    if site:
        last_runs = [r for r in last_runs if r.get("site") == site]

    return CrawlListResponse(
        current_run=_run_to_schema(current) if current else None,
        last_runs=[_run_to_schema(r) for r in last_runs[:limit]],
        total=len(last_runs),
    )


@router.get("/queue/depth", response_model=QueueDepthResponse, summary="RabbitMQ queue depths")
async def queue_depth():
    """
    Return approximate message counts for all active queues and DLQs.
    Requires RabbitMQ management plugin (CloudAMQP provides this).
    """
    from config.settings import settings
    from core.broker import get_sync_channel

    try:
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL)
        queues: dict[str, int] = {}
        dlqs: dict[str, int] = {}

        # Check known queue patterns
        from sdf_module.crawl_status import get_status
        status = get_status()
        known_runs = status.get("last_runs", [])[:10]
        pairs = {(r["project"], r["site"]) for r in known_runs if r.get("project") and r.get("site")}

        for project, site in pairs:
            for stage in ("discovery", "retriever", "parser"):
                from core.broker import queue_name, dlq_name
                q = queue_name(stage, site, project)
                try:
                    result = ch.queue_declare(queue=q, passive=True)
                    queues[q] = result.method.message_count
                except Exception:
                    pass

        for stage in ("discovery", "retriever", "parser"):
            from core.broker import dlq_name
            d = dlq_name(stage)
            try:
                result = ch.queue_declare(queue=d, passive=True)
                dlqs[d] = result.method.message_count
            except Exception:
                dlqs[d] = 0

        conn.close()
        return QueueDepthResponse(
            queues=queues,
            dlqs=dlqs,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RabbitMQ unavailable: {e}")


@router.get("/dlq/{stage}", response_model=DLQListResponse, summary="Browse dead-letter queue")
async def get_dlq(
    stage: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Peek at messages in the DLQ for a given stage (discovery/retriever/parser)."""
    if stage not in ("discovery", "retriever", "parser"):
        raise HTTPException(status_code=400, detail="stage must be discovery, retriever, or parser")

    from config.settings import settings
    from core.broker import dlq_name, get_sync_channel

    try:
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL)
        dlq = dlq_name(stage)
        messages = []

        for _ in range(limit):
            method, props, body = ch.basic_get(queue=dlq, auto_ack=False)
            if body is None:
                break
            try:
                payload = json.loads(body)
                dlq_meta = payload.get("_dlq", {})
                messages.append(DLQMessage(
                    url=payload.get("url", ""),
                    domain=payload.get("domain"),
                    site=payload.get("site"),
                    project=payload.get("project"),
                    failed_at=dlq_meta.get("failed_at"),
                    error=dlq_meta.get("error"),
                    retry_count=payload.get("_retry_count", 0),
                    raw=payload,
                ))
                # Nack without requeue so message stays in DLQ for inspection
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            except Exception:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        conn.close()
        return DLQListResponse(stage=stage, messages=messages, total=len(messages))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RabbitMQ unavailable: {e}")


@router.post("/dlq/{stage}/requeue", summary="Requeue DLQ messages for retry")
async def requeue_dlq(stage: str, limit: int = Query(100, ge=1, le=1000)):
    """
    Move messages from the DLQ back to the main stage queue for retry.
    Resets retry count.
    """
    if stage not in ("discovery", "retriever", "parser"):
        raise HTTPException(status_code=400, detail="Invalid stage")

    from config.settings import settings
    from core.broker import dlq_name, queue_name, get_sync_channel, EXCHANGE_RETRIEVER, EXCHANGE_PARSER, EXCHANGE_DISCOVERY, publish_sync

    exchange_map = {
        "discovery": EXCHANGE_DISCOVERY,
        "retriever": EXCHANGE_RETRIEVER,
        "parser":    EXCHANGE_PARSER,
    }

    try:
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL)
        dlq = dlq_name(stage)
        requeued = 0

        for _ in range(limit):
            method, props, body = ch.basic_get(queue=dlq, auto_ack=False)
            if body is None:
                break
            try:
                payload = json.loads(body)
                payload.pop("_dlq", None)
                payload["_retry_count"] = 0   # reset retry counter
                site = payload.get("site", "unknown")
                project = payload.get("project", "unknown")
                publish_sync(
                    ch,
                    exchange=exchange_map[stage],
                    routing_key=f"{stage}.{site}.{project}",
                    body=payload,
                    priority=3,
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
                requeued += 1
            except Exception as exc:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                logger.error("Requeue error: %s", exc)

        conn.close()
        return {"requeued": requeued, "stage": stage}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RabbitMQ unavailable: {e}")
