"""
SARA — RabbitMQ broker abstraction.

Provides:
  - Topology declaration (exchanges, queues, DLX) for all pipeline stages
  - Synchronous publisher/consumer (pika) — used by existing sync workers
  - Async publisher/consumer (aio_pika) — used by new async workers
  - Connection retry with exponential back-off

Queue naming convention:
  sara.{stage}.{site}_{project}   e.g. sara.retriever.myntra_com_commerce_crawl
Dead-letter:
  sara.dlq.{stage}                e.g. sara.dlq.retriever
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Callable

import pika  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXCHANGE_DISCOVERY = "sara.discovery"
EXCHANGE_RETRIEVER = "sara.retriever"
EXCHANGE_PARSER    = "sara.parser"
EXCHANGE_DLX       = "sara.dlx"

DLQ_RETRIEVER  = "sara.dlq.retriever"
DLQ_DISCOVERY  = "sara.dlq.discovery"
DLQ_PARSER     = "sara.dlq.parser"

MESSAGE_TTL_MS = 24 * 60 * 60 * 1_000   # 24h TTL on DLQ messages
MAX_PRIORITY   = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def queue_name(stage: str, site: str, project: str) -> str:
    return f"sara.{stage}.{site}_{project}"


def dlq_name(stage: str) -> str:
    return f"sara.dlq.{stage}"


# ---------------------------------------------------------------------------
# Synchronous helpers (pika) — backward-compatible with existing workers
# ---------------------------------------------------------------------------

def get_sync_channel(
    amqp_url: str,
    max_attempts: int = 5,
    base_backoff: float = 2.0,
) -> tuple[pika.BlockingConnection, pika.adapters.blocking_connection.BlockingChannel]:
    """Return a pika blocking connection+channel with retry."""
    params = pika.URLParameters(amqp_url)
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            return conn, ch
        except Exception as exc:
            last_exc = exc
            wait = base_backoff ** attempt
            logger.warning(
                "RabbitMQ connect attempt %d/%d failed (%s). Retrying in %.0fs.",
                attempt + 1, max_attempts, exc, wait,
            )
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def declare_pipeline_topology(channel, site: str, project: str) -> None:
    """
    Declare all exchanges, main queues, and dead-letter queues for one
    site/project pair.  Safe to call multiple times (idempotent).
    """
    # ── Dead-letter exchange (fanout) ─────────────────────────────────────
    channel.exchange_declare(
        exchange=EXCHANGE_DLX,
        exchange_type="topic",
        durable=True,
    )
    for stage in ("discovery", "retriever", "parser"):
        dlq = dlq_name(stage)
        channel.queue_declare(
            queue=dlq,
            durable=True,
            arguments={"x-message-ttl": MESSAGE_TTL_MS},
        )
        channel.queue_bind(
            queue=dlq,
            exchange=EXCHANGE_DLX,
            routing_key=f"dead.{stage}.#",
        )

    # ── Main exchanges ─────────────────────────────────────────────────────
    for exchange in (EXCHANGE_DISCOVERY, EXCHANGE_RETRIEVER, EXCHANGE_PARSER):
        channel.exchange_declare(
            exchange=exchange,
            exchange_type="topic",
            durable=True,
        )

    # ── Stage queues (with DLX routing + priority) ────────────────────────
    stage_exchange = {
        "discovery": EXCHANGE_DISCOVERY,
        "retriever": EXCHANGE_RETRIEVER,
        "parser":    EXCHANGE_PARSER,
    }
    for stage, exchange in stage_exchange.items():
        q = queue_name(stage, site, project)
        channel.queue_declare(
            queue=q,
            durable=True,
            arguments={
                "x-dead-letter-exchange":     EXCHANGE_DLX,
                "x-dead-letter-routing-key":  f"dead.{stage}.{site}.{project}",
                "x-max-priority":             MAX_PRIORITY,
            },
        )
        channel.queue_bind(
            queue=q,
            exchange=exchange,
            routing_key=f"{stage}.{site}.{project}",
        )


def publish_sync(
    channel,
    exchange: str,
    routing_key: str,
    body: dict,
    priority: int = 5,
) -> None:
    """Publish a JSON message synchronously."""
    channel.basic_publish(
        exchange=exchange,
        routing_key=routing_key,
        body=json.dumps(body).encode(),
        properties=pika.BasicProperties(
            delivery_mode=2,          # persistent
            priority=priority,
            content_type="application/json",
        ),
    )


# ---------------------------------------------------------------------------
# Async helpers (aio_pika) — used by new async workers
# ---------------------------------------------------------------------------

try:
    import aio_pika  # type: ignore

    class AsyncBroker:
        """
        Async RabbitMQ client wrapping aio_pika.
        One instance per worker process; call connect() once at startup.
        """

        def __init__(self, amqp_url: str):
            self._url = amqp_url
            self._conn: aio_pika.RobustConnection | None = None
            self._channel: aio_pika.Channel | None = None

        async def connect(self) -> None:
            self._conn = await aio_pika.connect_robust(
                self._url,
                reconnect_interval=5,
            )
            self._channel = await self._conn.channel()
            await self._channel.set_qos(prefetch_count=50)

        async def close(self) -> None:
            if self._conn:
                await self._conn.close()

        async def publish(
            self,
            exchange_name: str,
            routing_key: str,
            body: dict,
            priority: int = 5,
        ) -> None:
            assert self._channel, "Call connect() first"
            exchange = await self._channel.get_exchange(exchange_name)
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(body).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    priority=priority,
                    content_type="application/json",
                ),
                routing_key=routing_key,
            )

        async def consume(
            self,
            queue_name_: str,
            prefetch: int = 50,
        ) -> AsyncIterator[tuple[dict, Callable]]:
            """
            Async generator yielding (payload_dict, ack_fn) tuples.
            Call ack_fn() after successful processing.
            """
            assert self._channel, "Call connect() first"
            await self._channel.set_qos(prefetch_count=prefetch)
            queue = await self._channel.get_queue(queue_name_)
            async with queue.iterator() as q_iter:
                async for message in q_iter:
                    payload = json.loads(message.body)

                    async def _ack(msg=message):
                        await msg.ack()

                    yield payload, _ack

        async def send_to_dlq(
            self,
            stage: str,
            site: str,
            project: str,
            original_payload: dict,
            error: str,
        ) -> None:
            dlq_payload = {
                **original_payload,
                "_dlq": {
                    "stage": stage,
                    "error": error,
                    "failed_at": time.time(),
                },
            }
            await self.publish(
                EXCHANGE_DLX,
                routing_key=f"dead.{stage}.{site}.{project}",
                body=dlq_payload,
            )

except ImportError:
    # aio_pika not installed — async broker unavailable; sync workers still work
    class AsyncBroker:  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            raise ImportError(
                "aio_pika is required for async workers. "
                "Run: pip install aio-pika"
            )
