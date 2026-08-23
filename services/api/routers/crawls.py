"""
SARA API — Crawl management endpoints.

POST /crawls/trigger          — Publish a crawl job to sara-crawl-jobs queue
GET  /crawls/status           — Current + recent run status (all servers)
GET  /crawls/workers          — Live workers with current job info
GET  /crawls/queue/depth      — RabbitMQ queue depths
GET  /crawls/dlq/{stage}      — Browse dead-letter queue
POST /crawls/dlq/{stage}/requeue — Requeue DLQ messages
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import sys

from fastapi import APIRouter, Depends, HTTPException, Query

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
    WorkerInfo,
    WorkerListResponse,
)
from sdf_module.crawl_status import get_status

logger = logging.getLogger("sara.api.crawls")
router = APIRouter(prefix="/crawls", tags=["Crawls"])

JOB_QUEUE = "sara-crawl-jobs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        worker_id=r.get("worker_id"),
        hostname=r.get("hostname"),
        progress=r.get("progress", {}),
    )


def _get_redis():
    """Return a Redis client or None."""
    try:
        from config.settings import settings
        if not settings.REDIS_URL:
            return None
        import redis as _rl
        client = _rl.Redis.from_url(
            settings.REDIS_URL, decode_responses=True,
            socket_timeout=2, socket_connect_timeout=2,
        )
        client.ping()
        return client
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/trigger", summary="Launch a crawl pipeline")
async def trigger_crawl(req: CrawlTriggerRequest):
    """
    Publish a crawl job to the sara-crawl-jobs RabbitMQ queue.
    Any available worker will pick it up and execute the pipeline.
    This is the correct distributed mode — does NOT launch a local subprocess.
    """
    from config.settings import settings
    import pika

    schedule_id = req.schedule_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    job = {
        "project":       req.project,
        "site":          req.site,
        "schedule_id":   schedule_id,
        "priority":      req.priority,
        "use_async_worker": req.use_async_worker,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_by": "api",
    }

    try:
        params = pika.URLParameters(settings.CLOUDAMQP_URL)
        conn    = pika.BlockingConnection(params)
        ch      = conn.channel()
        ch.queue_declare(
            queue=JOB_QUEUE,
            durable=True,
            arguments={"x-max-priority": 10},
        )
        ch.basic_publish(
            exchange="",
            routing_key=JOB_QUEUE,
            body=json.dumps(job).encode(),
            properties=pika.BasicProperties(
                delivery_mode=2,          # persistent
                priority=req.priority,
            ),
        )
        conn.close()
        logger.info(
            "Job published: project=%s site=%s schedule=%s priority=%d",
            req.project, req.site, schedule_id, req.priority,
        )
    except Exception as exc:
        logger.error("Failed to publish crawl job: %s", exc)
        raise HTTPException(status_code=503, detail=f"RabbitMQ unavailable: {exc}")

    return {
        "message":     "Crawl job queued",
        "project":     req.project,
        "site":        req.site,
        "schedule_id": schedule_id,
        "priority":    req.priority,
        "queue":       JOB_QUEUE,
    }


@router.get("/status", response_model=CrawlListResponse, summary="List crawl runs")
async def list_crawls(
    project: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Return all active runs (across every connected server) and recent history.
    Multi-server aware: reads Redis which aggregates all server state.
    """
    data = get_status()

    # current_runs is a dict {run_key: run_dict}; current_run is the compat alias
    current_runs_dict: dict = data.get("current_runs", {})
    last_runs: list = data.get("last_runs", [])

    # Apply filters
    def _matches(r: dict) -> bool:
        if project and r.get("project") != project:
            return False
        if site and r.get("site") != site:
            return False
        return True

    current_runs = [_run_to_schema(r) for r in current_runs_dict.values() if _matches(r)]
    filtered_last = [_run_to_schema(r) for r in last_runs if _matches(r)][:limit]

    return CrawlListResponse(
        current_runs=current_runs,
        current_run=current_runs[0] if current_runs else None,
        last_runs=filtered_last,
        total=len(filtered_last),
    )


@router.get("/workers", response_model=WorkerListResponse, summary="Live worker registry")
async def list_workers():
    """
    Return all workers currently sending heartbeats to Redis.
    Shows hostname, worker_id, PID, start time, and current job (if any).
    Requires Redis to be configured — returns empty list if Redis is unavailable.
    """
    r = _get_redis()
    if r is None:
        return WorkerListResponse(workers=[], total=0)

    try:
        hb_keys = r.keys("sara:worker:*:heartbeat")
    except Exception:
        return WorkerListResponse(workers=[], total=0)

    workers: list[WorkerInfo] = []
    for hb_key in hb_keys:
        # Key format: sara:worker:{hostname}:{worker_id}:heartbeat
        parts = hb_key.split(":")
        if len(parts) < 5:
            continue
        hostname  = parts[2]
        worker_id = parts[3]
        prefix    = f"sara:worker:{hostname}:{worker_id}"

        try:
            last_seen_raw = r.get(hb_key)
            last_seen     = float(last_seen_raw) if last_seen_raw else None

            info_raw = r.get(f"{prefix}:info")
            info     = json.loads(info_raw) if info_raw else {}

            job_raw  = r.get(f"{prefix}:job")
            job      = json.loads(job_raw) if job_raw else None

            workers.append(WorkerInfo(
                worker_key=prefix,
                hostname=hostname,
                worker_id=worker_id,
                pid=info.get("pid"),
                started_at=info.get("started_at"),
                version=info.get("version"),
                last_seen=last_seen,
                current_job=job,
            ))
        except Exception as exc:
            logger.debug("Error reading worker info for %s: %s", prefix, exc)

    workers.sort(key=lambda w: (w.hostname, w.worker_id))
    return WorkerListResponse(workers=workers, total=len(workers))


@router.post("/dispatch/{project}/{site}", summary="Manually dispatch a crawl job")
async def dispatch_now(
    project: str,
    site: str,
    priority: int = Query(5, ge=1, le=10),
):
    """
    Immediately publish a one-shot crawl job to the queue, bypassing the schedule.
    Equivalent to: python -m services.scheduler.worker --dispatch-now PROJECT SITE
    """
    from config.settings import settings
    import pika
    from datetime import timezone

    schedule_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    job = {
        "project":       project,
        "site":          site,
        "schedule_id":   schedule_id,
        "priority":      priority,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_by": "api:dispatch_now",
    }

    try:
        params = pika.URLParameters(settings.CLOUDAMQP_URL)
        conn   = pika.BlockingConnection(params)
        ch     = conn.channel()
        ch.queue_declare(queue=JOB_QUEUE, durable=True, arguments={"x-max-priority": 10})
        ch.basic_publish(
            exchange="",
            routing_key=JOB_QUEUE,
            body=json.dumps(job).encode(),
            properties=pika.BasicProperties(delivery_mode=2, priority=priority),
        )
        conn.close()
        logger.info("Manual dispatch: %s/%s  schedule_id=%s  priority=%d", project, site, schedule_id, priority)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RabbitMQ unavailable: {exc}")

    return {"dispatched": True, "schedule_id": schedule_id, "project": project, "site": site, "priority": priority}


@router.get("/scheduler/dispatches", summary="Recent scheduler dispatch history")
async def scheduler_dispatches(limit: int = Query(20, ge=1, le=200)):
    """
    Return the most recent crawl job dispatches recorded by the scheduler in Redis.
    Only available when REDIS_URL is configured.
    """
    r = _get_redis()
    if r is None:
        return {"dispatches": [], "total": 0, "note": "Redis not configured"}

    try:
        # Sorted set — zrevrange gives most recent first (highest score = latest)
        entries = r.zrevrange("sara:scheduler:last_dispatched", 0, limit - 1, withscores=True)
        dispatches = []
        for member, score in entries:
            # member format: {project}__{site}__{schedule_id}
            parts = member.split("__", 2)
            detail = {"dispatched_ts": score, "member": member}
            if len(parts) == 3:
                detail["project"]     = parts[0]
                detail["site"]        = parts[1]
                detail["schedule_id"] = parts[2]
            dispatches.append(detail)
        return {"dispatches": dispatches, "total": len(dispatches)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}")


@router.get("/queue/depth", response_model=QueueDepthResponse, summary="RabbitMQ queue depths")
async def queue_depth():
    """
    Return approximate message counts for all active queues and DLQs.
    Requires RabbitMQ management plugin (CloudAMQP provides this).
    """
    from config.settings import settings
    from core.broker import get_sync_channel, queue_name, dlq_name

    try:
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL)
        queues: dict[str, int] = {}
        dlqs: dict[str, int] = {}

        # Job queue depth
        try:
            res = ch.queue_declare(queue=JOB_QUEUE, passive=True,
                                   arguments={"x-max-priority": 10})
            queues[JOB_QUEUE] = res.method.message_count
        except Exception:
            pass

        # Per-run stage queues from recent history
        status = get_status()
        known_runs = status.get("last_runs", [])[:10]
        pairs = {(r["project"], r["site"]) for r in known_runs if r.get("project") and r.get("site")}

        for project, site in pairs:
            for stage in ("discovery", "retriever", "parser"):
                q = queue_name(stage, site, project)
                try:
                    result = ch.queue_declare(queue=q, passive=True)
                    queues[q] = result.method.message_count
                except Exception:
                    pass

        # DLQs
        for stage in ("discovery", "retriever", "parser"):
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
                # Nack with requeue so message stays in DLQ for inspection
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
    from core.broker import (
        dlq_name, queue_name, get_sync_channel,
        EXCHANGE_RETRIEVER, EXCHANGE_PARSER, EXCHANGE_DISCOVERY, publish_sync,
    )

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
                site    = payload.get("site", "unknown")
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
