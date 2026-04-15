"""
URL Retriever — SARA pipeline stage 2.

Windowed streaming consumer:
  - Pulls _WINDOW_SIZE messages from RabbitMQ at a time (never loads all URLs into RAM)
  - Fetches each window concurrently with ThreadPoolExecutor
  - ACKs successes / NACKs failures from the MAIN THREAD only (pika is not thread-safe)
  - Failed messages are NACKed with requeue=False so they don't loop endlessly;
    configure a RabbitMQ dead-letter exchange on the queue for automatic DLQ routing.
  - Memory is O(WINDOW_SIZE * page_size), not O(total_urls * page_size).
  - Heartbeats are kept alive between windows via process_data_events().

Scale parameters (all tunable via env):
  NUM_FETCH_WORKERS                  parallel HTTP workers per window (default 8)
  DISCOVERY_BACKPRESSURE_THRESHOLD   not used here (only in discovery)
"""
from __future__ import annotations

from .sdf_fetch import *
from . import crawl_status
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import threading
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config.settings import settings as _settings
from core.rate_limiter import SyncDomainRateLimiter
from core.dedup import get_sync_dedup
from core.metrics import metrics

_rate_limiter = SyncDomainRateLimiter()

NUM_FETCH_WORKERS = _settings.NUM_FETCH_WORKERS
FETCH_SLEEP_SEC   = _settings.FETCH_SLEEP_SEC

# ── Windowed consumer tuning ────────────────────────────────────────────────
# Each window = one round of: basic_get × WINDOW_SIZE → ThreadPool → ACK/NACK
# Memory = WINDOW_SIZE × avg_page_size (not total_queue_depth × avg_page_size)
_WINDOW_SIZE        = max(NUM_FETCH_WORKERS * 2, 20)
_QUEUE_EMPTY_RETRIES = 10          # × _QUEUE_POLL_SLEEP seconds of idle tolerance
_QUEUE_POLL_SLEEP    = 5           # seconds between empty-queue polls
_HEARTBEAT_SECONDS   = 600         # pika connection heartbeat; keep > fetch timeout
_WORKER_TIMEOUT_SEC  = 300         # per-future timeout before logging a warning

# YAML field validation ─────────────────────────────────────────────────────
_KNOWN_REQUEST_PARAMS = frozenset({
    "extended_header", "max_retries", "timeout", "proxy",
    "user_agent", "cookies", "verify_ssl",
})


def _validate_yaml(content: dict, yaml_path: str) -> None:
    rp = content.get("request_params", {})
    unknown = set(rp.keys()) - _KNOWN_REQUEST_PARAMS
    if unknown:
        logging.warning(
            "YAML %s has unrecognised request_params fields %s — check for typos",
            yaml_path, sorted(unknown),
        )


class UrlRetriever:

    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlRetriever for project: {project_name} and site: {site_name}",
        )
        self.base_dir     = base_dir
        self.project_name = project_name
        self.site_name    = site_name

    def main(self, schedule_key: str) -> None:
        sdfFetch.set_crawl_context(
            stage="retriever",
            schedule_id=schedule_key,
            project=self.project_name,
            site=self.site_name,
        )
        sdfFetch.print_info_message(
            "info",
            f"[retriever] Starting for project={self.project_name}, "
            f"site={self.site_name}, schedule_id={schedule_key}",
        )

        # ── Load YAML config ─────────────────────────────────────────────────
        yaml_file_path = (
            Path(self.base_dir)
            / "url_discovery"
            / self.project_name
            / f"{self.site_name}_{self.project_name}.yml"
        )
        try:
            with open(yaml_file_path, "r", encoding="utf-8") as f:
                yaml_content = yaml.safe_load(f) or {}
        except FileNotFoundError:
            sdfFetch.print_error_message(
                "error", f"Retriever YAML not found: {yaml_file_path}"
            )
            return

        _validate_yaml(yaml_content, str(yaml_file_path))
        request_params  = yaml_content.get("request_params", {})
        extended_header = request_params.get("extended_header")
        max_retries     = request_params.get("max_retries", 3)
        timeout         = request_params.get("timeout", 30)
        proxy           = request_params.get("proxy")

        # ── Output paths ─────────────────────────────────────────────────────
        today        = date.today()
        formatted_dt = today.strftime("%Y%m%d")
        output_dir   = (
            Path(self.base_dir)
            / "scrape_output"
            / "retriever_output"
            / self.project_name
            / f"{self.site_name}_{self.project_name}"
            / schedule_key
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_file = output_dir / f"{schedule_key}_queue.txt"

        # ── Dedup ─────────────────────────────────────────────────────────────
        _cross_run_dedup = get_sync_dedup(self.project_name, self.site_name)
        _seen_this_run: set[str] = set()

        # ── Shared state (protected by fetch_lock) ────────────────────────────
        fetched_count = 0
        failed_count  = 0
        fetch_lock    = threading.Lock()

        # ── Per-URL fetch function (runs in thread pool) ──────────────────────
        def fetch_one(url_key: str) -> bool:
            """
            Fetch one URL. Returns True on success or dedup-skip, False on error.
            All shared-state writes are protected by fetch_lock.
            pika channel access is NEVER done here — only on the main thread.
            """
            nonlocal fetched_count, failed_count

            if not url_key:
                return True

            url    = url_key.split("|")[0]
            domain = urlparse(url).netloc or url

            # In-run dedup (fast, in-process)
            with fetch_lock:
                if url in _seen_this_run:
                    metrics.url_deduplicated(domain)
                    return True
                _seen_this_run.add(url)

            # Cross-run dedup (Redis / file, persisted across runs)
            try:
                if _cross_run_dedup.seen_sync(url):
                    metrics.url_deduplicated(domain)
                    logging.debug("Cross-run dedup skip: %s", url)
                    return True
            except Exception:
                pass  # dedup failure is non-fatal

            # Per-domain rate limiting
            try:
                _rate_limiter.acquire(domain)
            except Exception:
                sleep(FETCH_SLEEP_SEC)

            # HTTP fetch (timed for Prometheus)
            with metrics.fetch_timer(domain):
                result = sdfFetch.get_page_content_hash(
                    url,
                    proxy=proxy or None,
                    extended_header=extended_header or None,
                    max_retries=max_retries,
                    timeout=timeout,
                )

            output_file = str(output_dir / f"{formatted_dt}{sdfFetch.encode(url_key)}.html")
            data        = {"url": url_key, "output_file": output_file}
            success     = False

            if result["status_code"] == 200:
                content       = result["page_doc"]
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                with open(output_file, "wb") as fh:
                    fh.write(content_bytes)

                try:
                    _cross_run_dedup.add_sync(url)
                except Exception:
                    pass

                metrics.fetch_success(domain, self.project_name)
                with fetch_lock:
                    fetched_count += 1
                    crawl_status.update_progress(
                        self.project_name, self.site_name, schedule_key,
                        retriever_fetched=fetched_count,
                    )
                success = True
            else:
                error_type = (
                    f"http_{result['status_code']}"
                    if result["status_code"]
                    else "network_error"
                )
                metrics.fetch_failure(domain, error_type)
                logging.error(
                    "[retriever] Failed (%s): %s", result["status_code"], url
                )
                with fetch_lock:
                    failed_count += 1

            # Always write metadata entry so parser can log partial runs
            with fetch_lock:
                with open(metadata_file, "a", encoding="utf-8") as fh:
                    fh.write(str(data) + "\n")

            return success

        # ── Open persistent RabbitMQ connection ───────────────────────────────
        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        try:
            params = pika.URLParameters(CLOUDAMQP_URL)
            params.heartbeat = _HEARTBEAT_SECONDS
            connection = pika.BlockingConnection(params)
            channel    = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
        except Exception as exc:
            sdfFetch.print_error_message("error", f"RabbitMQ connect failed: {exc}")
            logging.exception("RabbitMQ connect failed")
            return

        # Announce queue depth at start
        try:
            q     = channel.queue_declare(queue=queue_name, durable=True, passive=True)
            depth = q.method.message_count
            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                stage="retriever", retriever_total=depth, retriever_fetched=0,
            )
            metrics.set_queue_depth(queue_name, depth)
            sdfFetch.print_info_message(
                "info",
                f"[retriever] Queue depth={depth} | window={_WINDOW_SIZE} | "
                f"workers={NUM_FETCH_WORKERS} | schedule_id={schedule_key}",
            )
        except Exception:
            pass

        empty_retries    = 0
        total_processed  = 0
        metrics.set_active_workers("retriever", NUM_FETCH_WORKERS)

        try:
            while True:
                # ── Keep connection alive between windows ─────────────────────
                try:
                    connection.process_data_events(time_limit=0)
                except Exception:
                    pass

                # ── Pull a window without auto-acking ─────────────────────────
                window: list[tuple[int, str]] = []
                for _ in range(_WINDOW_SIZE):
                    try:
                        method, _props, body = channel.basic_get(
                            queue=queue_name, auto_ack=False
                        )
                    except Exception as exc:
                        logging.warning("basic_get error: %s", exc)
                        break
                    if body is None:
                        break
                    window.append((method.delivery_tag, body.decode()))

                if not window:
                    empty_retries += 1
                    if empty_retries >= _QUEUE_EMPTY_RETRIES:
                        logging.info(
                            "[retriever] Queue empty after %d consecutive polls — done",
                            empty_retries,
                        )
                        break
                    sleep(_QUEUE_POLL_SLEEP)
                    continue
                empty_retries = 0

                # ── Fetch window concurrently ─────────────────────────────────
                results: list[tuple[int, bool]] = []
                results_lock = threading.Lock()

                def _process(delivery_tag: int, url_key: str) -> None:
                    ok = fetch_one(url_key)
                    with results_lock:
                        results.append((delivery_tag, ok))

                n_workers = min(NUM_FETCH_WORKERS, len(window))
                with ThreadPoolExecutor(max_workers=n_workers) as executor:
                    futs = [
                        executor.submit(_process, dt, uk)
                        for dt, uk in window
                    ]
                    for fut in as_completed(futs):
                        try:
                            fut.result(timeout=_WORKER_TIMEOUT_SEC)
                        except FuturesTimeoutError:
                            logging.error("Worker timed out (window item)")
                        except Exception:
                            logging.exception("Worker raised in window")

                # ── ACK / NACK from main thread only ──────────────────────────
                for delivery_tag, success in results:
                    try:
                        if success:
                            channel.basic_ack(delivery_tag=delivery_tag)
                        else:
                            # requeue=False: don't loop on permanent failures.
                            # Configure a dead-letter exchange on the queue for
                            # automatic routing of these to sara-dlq.
                            channel.basic_nack(
                                delivery_tag=delivery_tag, requeue=False
                            )
                    except Exception as exc:
                        logging.warning(
                            "ACK/NACK failed for tag=%d: %s", delivery_tag, exc
                        )

                total_processed += len(window)
                logging.info(
                    "[retriever] Window complete | window=%d total_processed=%d "
                    "fetched=%d failed=%d",
                    len(window), total_processed, fetched_count, failed_count,
                )

                # Update queue depth metric periodically
                if total_processed % (_WINDOW_SIZE * 10) == 0:
                    try:
                        q     = channel.queue_declare(queue=queue_name, durable=True, passive=True)
                        depth = q.method.message_count
                        metrics.set_queue_depth(queue_name, depth)
                    except Exception:
                        pass

        finally:
            metrics.set_active_workers("retriever", 0)
            # Delete queue and close connection on exit (success or exception)
            try:
                channel.queue_delete(queue=queue_name)
                logging.info("Deleted RabbitMQ queue: %s", queue_name)
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

        sdfFetch.print_info_message(
            "success",
            f"[retriever] Completed schedule_id={schedule_key} | "
            f"Fetched={fetched_count} Failed={failed_count} "
            f"Total={total_processed}",
        )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python -m sdf_module.url_retriever <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir      = Path(__file__).resolve().parent.parent
    project_name  = sys.argv[1]
    site_name     = sys.argv[2]
    schedule_key  = sys.argv[3]
    url_retriever = UrlRetriever(base_dir, project_name, site_name)
    url_retriever.main(schedule_key)
