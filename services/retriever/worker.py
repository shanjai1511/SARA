"""
SARA — Async Retriever Worker.

Replaces the synchronous ThreadPoolExecutor-based retriever with a fully
async aiohttp implementation.  Consumes URLs from RabbitMQ, fetches HTML
concurrently (bounded semaphore), stores raw HTML, and publishes to the
parser queue.

Run one worker process per site/project, or multiplex multiple sites in one
process using asyncio task groups.

Entry point:
    python -m services.retriever.worker --project commerce_crawl --site myntra_com --schedule 20260405

Key improvements over the sync retriever:
  - aiohttp: non-blocking HTTP → 10-20× higher concurrency per process
  - Smart proxy rotation via core.proxy_manager
  - Per-domain rate limiting via core.rate_limiter (Redis-backed, cross-pod)
  - URL deduplication via core.dedup (Redis Bloom filter)
  - Content-change detection: skips parser queue if page unchanged
  - Prometheus metrics on /metrics
  - Dead-letter queue for exhausted retries
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import settings
from core.broker import (
    AsyncBroker,
    EXCHANGE_PARSER,
    declare_pipeline_topology,
    get_sync_channel,
    queue_name,
)
from core.change_detection import get_change_store
from core.metrics import metrics, start_metrics_server
from core.proxy_manager import ProxyManager
from core.rate_limiter import DomainRateLimiter
from core.storage import get_storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sara.retriever")

# ---------------------------------------------------------------------------
# User-agent pool (realistic browser UAs)
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# Error codes that warrant a retry (transient)
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Error codes that mean the URL is permanently unreachable (don't retry)
PERMANENT_ERRORS = {404, 410}


# ---------------------------------------------------------------------------
# Core fetch function
# ---------------------------------------------------------------------------

async def fetch_url(
    session,
    url: str,
    proxy: Optional[str],
    max_retries: int = 3,
    timeout_sec: int = 30,
) -> dict:
    """
    Fetch a single URL with retry + exponential back-off.
    Returns dict with keys: status, html, error, latency_ms
    """
    import aiohttp

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    timeout = aiohttp.ClientTimeout(total=timeout_sec, connect=10)
    last_exc: Optional[Exception] = None
    last_status: Optional[int] = None

    for attempt in range(max_retries + 1):
        t0 = time.monotonic()
        try:
            async with session.get(
                url,
                headers=headers,
                proxy=proxy,
                timeout=timeout,
                allow_redirects=True,
                ssl=False,
            ) as resp:
                latency_ms = int((time.monotonic() - t0) * 1000)
                last_status = resp.status

                if resp.status == 200:
                    html = await resp.text(encoding="utf-8", errors="replace")
                    return {
                        "status": 200,
                        "html": html,
                        "error": None,
                        "latency_ms": latency_ms,
                    }

                if resp.status in PERMANENT_ERRORS:
                    return {
                        "status": resp.status,
                        "html": "",
                        "error": f"permanent_error_{resp.status}",
                        "latency_ms": latency_ms,
                    }

                if resp.status in RETRYABLE_STATUSES and attempt < max_retries:
                    backoff = min(2 ** attempt * 5, 60) + random.uniform(0, 2)
                    logger.info(
                        "HTTP %d for %s — retrying in %.1fs (attempt %d/%d)",
                        resp.status, url, backoff, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(backoff)
                    continue

                return {
                    "status": resp.status,
                    "html": "",
                    "error": f"http_{resp.status}",
                    "latency_ms": latency_ms,
                }

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_exc = exc
            latency_ms = int((time.monotonic() - t0) * 1000)
            if attempt < max_retries:
                backoff = min(2 ** attempt * 3, 30) + random.uniform(0, 1)
                logger.warning(
                    "Fetch error %s for %s — retrying in %.1fs",
                    type(exc).__name__, url, backoff,
                )
                await asyncio.sleep(backoff)
            else:
                logger.error("Fetch failed after %d attempts: %s — %s", max_retries + 1, url, exc)

    return {
        "status": last_status or -1,
        "html": "",
        "error": str(last_exc) if last_exc else "unknown",
        "latency_ms": 0,
    }


# ---------------------------------------------------------------------------
# Worker class
# ---------------------------------------------------------------------------

class AsyncRetrieverWorker:
    """
    Consumes URLs from the retriever queue, fetches HTML, stores it,
    and publishes parse tasks to the parser queue.
    """

    def __init__(
        self,
        project: str,
        site: str,
        schedule_id: str,
        concurrency: int = 20,
    ):
        self.project = project
        self.site = site
        self.schedule_id = schedule_id
        self.concurrency = concurrency
        self.domain = f"{site.replace('_', '.').replace('-', '.')}"

        self.proxy_mgr = ProxyManager.from_env()
        self.storage = get_storage(base_dir=ROOT / "scrape_output" / "raw_html")
        self.change_store = get_change_store(
            path=ROOT / "logs" / "change_state.json"
        )

        # Stats
        self._fetched = 0
        self._failed = 0
        self._skipped_unchanged = 0
        self._start_time = time.time()

    async def run(self) -> None:
        import aiohttp

        logger.info(
            "[retriever] Starting async worker: project=%s site=%s schedule=%s concurrency=%d",
            self.project, self.site, self.schedule_id, self.concurrency,
        )

        # Declare RabbitMQ topology (idempotent)
        conn, ch = get_sync_channel(settings.CLOUDAMQP_URL)
        declare_pipeline_topology(ch, self.site, self.project)
        conn.close()

        # Try to get Redis for rate limiting and dedup
        rate_limiter = None
        try:
            redis_url = getattr(settings, "REDIS_URL", None)
            if redis_url:
                from redis.asyncio import Redis as ARedis
                from core.dedup import BloomFilter
                redis = ARedis.from_url(redis_url, decode_responses=False)
                rate_limiter = DomainRateLimiter(redis)
                self._bloom = BloomFilter(redis, f"sara:dedup:retriever:{self.project}")
                logger.info("Rate limiter + Bloom filter: Redis connected")
        except Exception as e:
            logger.warning("Redis unavailable (%s) — rate limiting disabled", e)
            self._bloom = None

        semaphore = asyncio.Semaphore(self.concurrency)
        connector = aiohttp.TCPConnector(
            limit=self.concurrency + 10,
            limit_per_host=5,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            ssl=False,
        )
        q_name = queue_name("retriever", self.site, self.project)

        async with aiohttp.ClientSession(connector=connector) as session:
            broker = AsyncBroker(settings.CLOUDAMQP_URL)
            await broker.connect()

            tasks = []
            async for payload, ack in broker.consume(q_name, prefetch=self.concurrency):
                url = payload.get("url", "")
                if not url:
                    await ack()
                    continue

                # Bloom filter dedup
                if self._bloom and await self._bloom.seen(url):
                    metrics.url_deduplicated(self.domain)
                    await ack()
                    continue

                task = asyncio.create_task(
                    self._process(
                        session, broker, rate_limiter, semaphore, payload, ack
                    )
                )
                tasks.append(task)

                # Clean up done tasks periodically
                tasks = [t for t in tasks if not t.done()]

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await broker.close()

        elapsed = time.time() - self._start_time
        logger.info(
            "[retriever] Completed: fetched=%d failed=%d unchanged=%d elapsed=%.1fs",
            self._fetched, self._failed, self._skipped_unchanged, elapsed,
        )

    async def _process(
        self,
        session,
        broker: AsyncBroker,
        rate_limiter: Optional[DomainRateLimiter],
        semaphore: asyncio.Semaphore,
        payload: dict,
        ack,
    ) -> None:
        url = payload["url"]
        domain = urlparse(url).netloc

        async with semaphore:
            # Rate limit
            if rate_limiter:
                await rate_limiter.acquire(domain)

            # Proxy selection
            proxy = self.proxy_mgr.get_proxy_for_request(domain)

            with metrics.fetch_timer(domain):
                result = await fetch_url(session, url, proxy)

            if result["status"] == 200:
                html = result["html"]
                metrics.fetch_success(domain, self.project)

                # Change detection — skip parser if unchanged
                change = self.change_store.check_and_update(url, html)
                if not change.changed:
                    self._skipped_unchanged += 1
                    logger.debug("Unchanged: %s", url)
                    await ack()
                    return

                # Store raw HTML
                try:
                    key = self.storage.put_html(url, html, project=self.project)
                except Exception as e:
                    logger.error("Storage failed for %s: %s", url, e)
                    key = None

                # Add to Bloom filter (mark as seen)
                if self._bloom:
                    await self._bloom.add(url)

                # Publish to parser queue
                parse_payload = {
                    **payload,
                    "storage_key": key,
                    "content_hash": change.new_hash,
                    "change_type": change.change_type.value,
                    "fetched_at": time.time(),
                    "latency_ms": result["latency_ms"],
                }
                await broker.publish(
                    EXCHANGE_PARSER,
                    routing_key=f"parser.{self.site}.{self.project}",
                    body=parse_payload,
                )
                self._fetched += 1
                self.proxy_mgr.report_success(domain, proxy or "direct")

            else:
                error = result["error"] or f"http_{result['status']}"
                metrics.fetch_failure(domain, error)
                self.proxy_mgr.report_failure(
                    domain,
                    proxy or "direct",
                    blocked=(result["status"] in (403, 429)),
                )
                self._failed += 1

                # Increment retry count and re-queue or DLQ
                retry_count = payload.get("_retry_count", 0) + 1
                if retry_count < 3 and result["status"] not in PERMANENT_ERRORS:
                    payload["_retry_count"] = retry_count
                    await broker.publish(
                        "sara.retriever",
                        routing_key=f"retriever.{self.site}.{self.project}",
                        body=payload,
                        priority=2,   # lower priority for retries
                    )
                else:
                    await broker.send_to_dlq(
                        "retriever", self.site, self.project, payload, error
                    )
                    metrics.dlq_message("retriever", domain)

            await ack()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    parser = argparse.ArgumentParser(description="SARA Async Retriever Worker")
    parser.add_argument("--project",  required=True)
    parser.add_argument("--site",     required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--concurrency", type=int,
                        default=int(os.environ.get("NUM_FETCH_WORKERS", 20)))
    parser.add_argument("--metrics-port", type=int, default=8001)
    args = parser.parse_args()

    start_metrics_server(port=args.metrics_port)

    worker = AsyncRetrieverWorker(
        project=args.project,
        site=args.site,
        schedule_id=args.schedule,
        concurrency=args.concurrency,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
