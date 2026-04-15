"""
URL Discovery — SARA pipeline stage 1.

Scale improvements over sequential baseline:
  - Within each depth level, URLs are fetched in parallel via ThreadPoolExecutor
    (NUM_DISCOVERY_WORKERS workers, default 6 — tune via env).
  - Backpressure: before publishing a batch, checks RabbitMQ queue depth.
    If depth > DISCOVERY_BACKPRESSURE_THRESHOLD, pauses publishing until
    the retriever drains the queue.  Prevents the queue from growing unboundedly
    when retrieval is slower than discovery.
  - YAML field validation: warns on unrecognised keys so typos surface immediately.
  - Metrics: records urls_discovered counter per batch pushed.
"""
from .sdf_fetch import *
from . import crawl_status
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse

from config.settings import settings as _settings
from core.rate_limiter import SyncDomainRateLimiter
from core.metrics import metrics

_rate_limiter = SyncDomainRateLimiter()

NUM_DISCOVERY_WORKERS          = _settings.NUM_DISCOVERY_WORKERS
_BACKPRESSURE_THRESHOLD        = _settings.DISCOVERY_BACKPRESSURE_THRESHOLD
_BACKPRESSURE_SLEEP            = 10    # seconds to wait when queue is over threshold
_PUBLISH_BATCH                 = 100   # URLs per RabbitMQ batch
_WORKER_TIMEOUT_SEC            = 60    # per-URL discovery timeout

# YAML field validation ─────────────────────────────────────────────────────
_KNOWN_DEPTH_KEYS  = frozenset({"seed_url", "method_name", "limit", "max_depth"})
_KNOWN_PARAM_KEYS  = frozenset({"request_params", "depth0"})


def _validate_yaml(content: dict, yaml_path: str) -> None:
    for key, value in content.items():
        if key.startswith("depth") and isinstance(value, dict):
            unknown = set(value.keys()) - _KNOWN_DEPTH_KEYS
            if unknown:
                logging.warning(
                    "YAML %s section '%s' has unrecognised keys %s — check for typos",
                    yaml_path, key, sorted(unknown),
                )


class UrlDiscovery:
    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlDiscovery for project: {project_name} and site: {site_name}",
        )
        self.base_dir     = base_dir
        self.output_dir   = ""
        self.collector_dir = ""
        self.project_name = project_name
        self.site_name    = site_name
        self.count        = 0

    # ── Backpressure ─────────────────────────────────────────────────────────

    def _queue_depth(self, queue_name: str) -> int:
        """Return current RabbitMQ queue depth, or 0 on error."""
        try:
            conn = pika.BlockingConnection(pika.URLParameters(CLOUDAMQP_URL))
            ch   = conn.channel()
            q    = ch.queue_declare(queue=queue_name, durable=True, passive=True)
            depth = q.method.message_count
            conn.close()
            return depth
        except Exception:
            return 0

    def _wait_for_backpressure(self, queue_name: str) -> None:
        """Block until queue depth drops below threshold."""
        while True:
            depth = self._queue_depth(queue_name)
            metrics.set_queue_depth(queue_name, depth)
            if depth < _BACKPRESSURE_THRESHOLD:
                return
            logging.info(
                "[discovery] Backpressure: queue depth %d >= %d — pausing %ds",
                depth, _BACKPRESSURE_THRESHOLD, _BACKPRESSURE_SLEEP,
            )
            sleep(_BACKPRESSURE_SLEEP)

    # ── RabbitMQ publish ──────────────────────────────────────────────────────

    def push_urls_to_queue(self, result_url: List[str], schedule_key: str) -> None:
        """Push URLs to RabbitMQ in batches.  Applies backpressure before each batch."""
        if not result_url:
            return

        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        sdfFetch.print_info_message(
            "info",
            f"Pushing {len(result_url)} URLs to RabbitMQ for "
            f"{self.project_name}/{self.site_name}",
        )

        connection = None
        try:
            connection, channel = sdfFetch.get_rabbitmq_channel()
            channel.queue_declare(queue=queue_name, durable=True)

            for i in range(0, len(result_url), _PUBLISH_BATCH):
                batch = result_url[i: i + _PUBLISH_BATCH]

                # Backpressure: pause if retriever can't keep up
                self._wait_for_backpressure(queue_name)

                for url in batch:
                    channel.basic_publish(
                        exchange="",
                        routing_key=queue_name,
                        body=url.encode(),
                        properties=pika.BasicProperties(delivery_mode=2),
                    )

                domain = urlparse(batch[0]).netloc or batch[0] if batch else "unknown"
                metrics.url_discovered(domain, self.project_name)
                logging.debug("Published batch %d-%d to %s", i, i + len(batch), queue_name)

            sdfFetch.print_info_message(
                "success",
                f"Pushed {len(result_url)} URLs to queue {queue_name}",
            )
        except Exception:
            logging.exception("Failed to push URLs to RabbitMQ")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def write_url_in_txt(self, result_url: List[str], schedule_key: str) -> None:
        filepath = Path(self.output_dir) / f"{self.site_name}_{self.project_name}_{schedule_key}.txt"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "a") as f:
            for item in result_url:
                f.write(f"{item}\n")

    # ── Parallel within-level URL fetching ────────────────────────────────────

    def get_urls_by_depth(
        self,
        urls: List[str],
        depth: dict,
        module_instance: Any,
        schedule_key: str,
    ) -> None:
        if not urls:
            sdfFetch.print_error_message("error", "No seed URLs provided for discovery stage.")
            return

        depth_items = sorted(
            (
                (int(key.replace("depth", "")), value)
                for key, value in depth.items()
                if key.startswith("depth") and key != "depth0"
            ),
            key=lambda item: item[0],
        )

        pending_urls = list(urls)
        for current_level, current_depth in depth_items:
            if not isinstance(current_depth, dict):
                continue
            method_name = current_depth.get("method_name")
            if not method_name:
                sdfFetch.print_error_message(
                    "error", f"Missing method_name for depth level {current_level}."
                )
                return

            method_to_call = getattr(module_instance, method_name, None)
            if not callable(method_to_call):
                logging.warning("No method '%s' found on %s", method_name, module_instance)
                return

            sdfFetch.print_info_message(
                "info",
                f"[discovery] depth{current_level}: {len(pending_urls)} URLs "
                f"| method={method_name} | workers={NUM_DISCOVERY_WORKERS}",
            )

            next_urls: List[str] = []
            next_lock = threading.Lock()

            def _fetch_url(url: str) -> None:
                """Fetch one URL in the discovery depth level."""
                try:
                    domain = urlparse(url).netloc or url
                    _rate_limiter.acquire(domain)
                except Exception:
                    sleep(_settings.FETCH_DELAY)

                try:
                    result_url = method_to_call(url, depth, current_level)
                    if isinstance(result_url, str):
                        result_url = [result_url]
                    elif result_url is None:
                        result_url = []
                    with next_lock:
                        next_urls.extend(result_url)
                except Exception as e:
                    sdfFetch.print_error_message(
                        "error", f"URL fetching failed for {url}: {e}"
                    )
                    logging.exception("URL fetching failed")

            n_workers = min(NUM_DISCOVERY_WORKERS, len(pending_urls))
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futs = {executor.submit(_fetch_url, url): url for url in pending_urls}
                for fut in as_completed(futs):
                    try:
                        fut.result(timeout=_WORKER_TIMEOUT_SEC)
                    except FuturesTimeoutError:
                        logging.error("Discovery worker timed out for %s", futs[fut])
                    except Exception:
                        logging.exception("Discovery worker failed for %s", futs[fut])

            sdfFetch.print_info_message(
                "info",
                f"[discovery] depth{current_level} complete: {len(next_urls)} URLs found",
            )

            # Push to queue at the final depth level
            if current_level == depth_items[-1][0]:
                self.push_urls_to_queue(next_urls, schedule_key)
                self.count += len(next_urls)

            pending_urls = next_urls

    def main_execution(self, schedule_key: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Starting main execution for {self.project_name}/{self.site_name}",
        )
        try:
            yaml_file_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.yml"
            with open(yaml_file_path, "r", encoding="utf-8") as f:
                depth = yaml.safe_load(f) or {}

            _validate_yaml(depth, str(yaml_file_path))

            module_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.py"
            class_name  = normalize_class_name(self.project_name, self.site_name)

            try:
                spec   = importlib.util.spec_from_file_location(class_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                SiteClass     = getattr(module, class_name)
                site_instance = SiteClass()
            except Exception as e:
                sdfFetch.print_error_message(
                    "error", f"Error importing module from {module_path}: {e}"
                )
                logging.exception("Module import failed")
                return

            seed_url = depth.get("depth0", {}).get("seed_url")
            if not seed_url:
                sdfFetch.print_error_message("error", "depth0.seed_url is missing or empty.")
                return

            self.get_urls_by_depth(seed_url, depth, site_instance, schedule_key)

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
            logging.exception("Unhandled error during execution")
            raise

    def main(self, schedule_key: str) -> None:
        sdfFetch.set_crawl_context(
            stage="discovery",
            schedule_id=schedule_key,
            project=self.project_name,
            site=self.site_name,
        )
        sdfFetch.print_info_message(
            "info",
            f"[discovery] Starting for project={self.project_name}, "
            f"site={self.site_name}, schedule_id={schedule_key}",
        )
        self.output_dir    = Path(self.base_dir) / f"scrape_output/discovery_output/{self.project_name}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.collector_dir = Path(self.base_dir) / f"url_discovery/{self.project_name}"

        # Clear previous discovery output for this schedule
        filepath = self.output_dir / f"{self.site_name}_{self.project_name}_{schedule_key}.txt"
        filepath.write_text("")

        self.main_execution(schedule_key)
        crawl_status.update_progress(
            self.project_name, self.site_name, schedule_key,
            stage="discovery", discovery_urls=self.count,
        )
        sdfFetch.print_info_message(
            "success",
            f"[discovery] Completed schedule_id={schedule_key} | URLs discovered: {self.count}",
        )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python -m sdf_module.url_discovery <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir      = Path(__file__).resolve().parent.parent
    project_name  = sys.argv[1]
    site_name     = sys.argv[2]
    schedule_key  = sys.argv[3]
    url_discovery = UrlDiscovery(base_dir, project_name, site_name)
    url_discovery.main(schedule_key)
