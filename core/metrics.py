"""
SARA — Prometheus metrics instrumentation.

All metrics are registered once at module load time.
Import this module in each worker service; the /metrics HTTP endpoint
is served by a small background thread (start_metrics_server).

Usage:
    from core.metrics import metrics, start_metrics_server
    start_metrics_server(port=8000)   # once at worker startup

    metrics.fetch_success("myntra.com")
    metrics.fetch_failure("ajio.com", "timeout")
    with metrics.fetch_latency("flipkart.com").time():
        ...
"""
from __future__ import annotations

import logging
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (  # type: ignore
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed — metrics disabled")


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

if _PROMETHEUS_AVAILABLE:

    # ── Throughput counters ────────────────────────────────────────────────
    PAGES_FETCHED = Counter(
        "sara_pages_fetched_total",
        "Pages successfully fetched (HTTP 200)",
        ["domain", "project"],
    )
    FETCH_ERRORS = Counter(
        "sara_fetch_errors_total",
        "Page fetch failures",
        ["domain", "error_type"],
    )
    RECORDS_PARSED = Counter(
        "sara_records_parsed_total",
        "Structured records successfully extracted",
        ["domain", "project"],
    )
    URLS_DISCOVERED = Counter(
        "sara_urls_discovered_total",
        "URLs pushed to retriever queue",
        ["domain", "project"],
    )
    URLS_DEDUPLICATED = Counter(
        "sara_urls_deduplicated_total",
        "URLs skipped because already seen (Bloom filter)",
        ["domain"],
    )
    DLQ_MESSAGES = Counter(
        "sara_dlq_messages_total",
        "Messages moved to dead-letter queue",
        ["stage", "domain"],
    )

    # ── Latency histograms ─────────────────────────────────────────────────
    FETCH_LATENCY = Histogram(
        "sara_fetch_duration_seconds",
        "HTTP fetch wall-clock time",
        ["domain"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
    )
    PARSE_LATENCY = Histogram(
        "sara_parse_duration_seconds",
        "HTML parsing and extraction wall-clock time",
        ["domain"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
    )
    QUEUE_PUBLISH_LATENCY = Histogram(
        "sara_queue_publish_duration_seconds",
        "Time to publish a message to RabbitMQ",
        ["exchange"],
        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
    )

    # ── Gauges ────────────────────────────────────────────────────────────
    ACTIVE_WORKERS = Gauge(
        "sara_active_workers",
        "Number of active async fetch coroutines",
        ["stage"],
    )
    PROXY_HEALTH = Gauge(
        "sara_proxy_healthy_count",
        "Number of proxies with success_rate >= 0.5",
    )
    PROXY_SUCCESS_RATE = Gauge(
        "sara_proxy_avg_success_rate",
        "Average success rate across all proxies",
    )
    QUEUE_DEPTH = Gauge(
        "sara_queue_depth",
        "Approximate messages waiting in RabbitMQ queue",
        ["queue"],
    )
    CRAWL_SUCCESS_RATE = Gauge(
        "sara_crawl_success_rate_pct",
        "Rolling crawl success rate (%) last 5 minutes",
        ["domain"],
    )


# ---------------------------------------------------------------------------
# Convenience facade
# ---------------------------------------------------------------------------

class _NoOpMetrics:
    """Returned when prometheus_client is not installed."""

    class _NoOp:
        def inc(self, *a, **kw): pass
        def set(self, *a, **kw): pass
        def observe(self, *a, **kw): pass
        def time(self):
            from contextlib import contextmanager
            @contextmanager
            def _ctx():
                yield
            return _ctx()

    def __getattr__(self, _):
        return self._NoOp()


class Metrics:
    """High-level metrics facade used by worker code."""

    def fetch_success(self, domain: str, project: str = "unknown") -> None:
        if _PROMETHEUS_AVAILABLE:
            PAGES_FETCHED.labels(domain=domain, project=project).inc()

    def fetch_failure(self, domain: str, error_type: str) -> None:
        if _PROMETHEUS_AVAILABLE:
            FETCH_ERRORS.labels(domain=domain, error_type=error_type).inc()

    def record_parsed(self, domain: str, project: str = "unknown") -> None:
        if _PROMETHEUS_AVAILABLE:
            RECORDS_PARSED.labels(domain=domain, project=project).inc()

    def url_discovered(self, domain: str, project: str = "unknown") -> None:
        if _PROMETHEUS_AVAILABLE:
            URLS_DISCOVERED.labels(domain=domain, project=project).inc()

    def url_deduplicated(self, domain: str) -> None:
        if _PROMETHEUS_AVAILABLE:
            URLS_DEDUPLICATED.labels(domain=domain).inc()

    def dlq_message(self, stage: str, domain: str) -> None:
        if _PROMETHEUS_AVAILABLE:
            DLQ_MESSAGES.labels(stage=stage, domain=domain).inc()

    def fetch_timer(self, domain: str):
        """Context manager: times a fetch block."""
        if _PROMETHEUS_AVAILABLE:
            return FETCH_LATENCY.labels(domain=domain).time()
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()

    def parse_timer(self, domain: str):
        if _PROMETHEUS_AVAILABLE:
            return PARSE_LATENCY.labels(domain=domain).time()
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()

    def set_active_workers(self, stage: str, count: int) -> None:
        if _PROMETHEUS_AVAILABLE:
            ACTIVE_WORKERS.labels(stage=stage).set(count)

    def set_proxy_health(self, healthy: int, avg_rate: float) -> None:
        if _PROMETHEUS_AVAILABLE:
            PROXY_HEALTH.set(healthy)
            PROXY_SUCCESS_RATE.set(avg_rate)

    def set_queue_depth(self, queue: str, depth: int) -> None:
        if _PROMETHEUS_AVAILABLE:
            QUEUE_DEPTH.labels(queue=queue).set(depth)


# Module-level singleton
metrics = Metrics()


# ---------------------------------------------------------------------------
# Metrics HTTP server (background thread)
# ---------------------------------------------------------------------------

def start_metrics_server(port: int = 8000) -> None:
    """Start a lightweight HTTP server exposing /metrics on the given port."""
    if not _PROMETHEUS_AVAILABLE:
        logger.warning("Metrics server not started — prometheus_client unavailable")
        return

    class _SilentHandler(WSGIRequestHandler):
        def log_message(self, *args): pass   # suppress access logs

    def _app(environ, start_response):
        if environ["PATH_INFO"] == "/metrics":
            output = generate_latest()
            start_response("200 OK", [
                ("Content-Type", CONTENT_TYPE_LATEST),
                ("Content-Length", str(len(output))),
            ])
            return [output]
        start_response("404 Not Found", [])
        return [b"Not found"]

    def _serve():
        try:
            httpd = make_server("0.0.0.0", port, _app, handler_class=_SilentHandler)
            logger.info("Prometheus metrics server listening on :%d/metrics", port)
            httpd.serve_forever()
        except OSError as e:
            logger.warning("Could not start metrics server on port %d: %s", port, e)

    t = threading.Thread(target=_serve, daemon=True, name="metrics-server")
    t.start()
