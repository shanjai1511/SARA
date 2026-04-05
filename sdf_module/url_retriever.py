from .sdf_fetch import *
from . import crawl_status
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import threading
import logging
from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse

from config.settings import settings as _settings
from core.rate_limiter import SyncDomainRateLimiter
from core.dedup import get_sync_dedup

_rate_limiter = SyncDomainRateLimiter()

NUM_FETCH_WORKERS = _settings.NUM_FETCH_WORKERS
FETCH_SLEEP_SEC   = _settings.FETCH_SLEEP_SEC

# Fix 3: no hard cap — drain the queue completely.
# Use a large sentinel so the while-loop naturally exits only when the
# queue is empty (MAX_EMPTY_RETRIES consecutive empty polls).
_QUEUE_EMPTY_RETRIES = 10   # × 5 s = 50 s max wait for late-arriving URLs
_QUEUE_POLL_SLEEP    = 5    # seconds between empty-queue polls


class UrlRetriever:

    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlRetriever for project: {project_name} and site: {site_name}",
        )
        self.base_dir     = base_dir
        self.output_dir   = ""
        self.project_name = project_name
        self.site_name    = site_name

    def fetch_retriever_output(self, schedule_key: str) -> List[str]:
        """Drain the RabbitMQ queue completely — no hard URL count cap."""
        sdfFetch.print_info_message(
            "info",
            f"Draining queue for {self.project_name}/{self.site_name}",
        )

        urls: List[str] = []
        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        connection = None

        try:
            connection, channel = sdfFetch.get_rabbitmq_channel()
            channel.queue_declare(queue=queue_name, durable=True)

            empty_retries = 0
            while True:
                method, properties, body = channel.basic_get(queue=queue_name)
                if body is None:
                    empty_retries += 1
                    if empty_retries >= _QUEUE_EMPTY_RETRIES:
                        break           # queue is truly empty
                    sleep(_QUEUE_POLL_SLEEP)
                    continue
                empty_retries = 0
                urls.append(body.decode())
                channel.basic_ack(delivery_tag=method.delivery_tag)

            # Delete the queue once fully consumed to avoid stale accumulation
            try:
                channel.queue_delete(queue=queue_name)
                logging.info("Deleted RabbitMQ queue: %s", queue_name)
            except Exception:
                pass

        except Exception as e:
            sdfFetch.print_error_message("error", str(e))
            logging.exception("RabbitMQ fetch failed")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

        return urls

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

        request_params  = yaml_content.get("request_params", {})
        extended_header = request_params.get("extended_header")
        max_retries     = request_params.get("max_retries", 3)
        timeout         = request_params.get("timeout", 30)
        proxy           = request_params.get("proxy")

        output_queue = self.fetch_retriever_output(schedule_key)
        total_urls   = len(output_queue)
        crawl_status.update_progress(
            self.project_name, self.site_name, schedule_key,
            stage="retriever", retriever_total=total_urls, retriever_fetched=0,
        )
        sdfFetch.print_info_message(
            "info",
            f"[retriever] {total_urls} URLs pulled from queue for schedule_id={schedule_key}",
        )

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

        # Fix 7: cross-run dedup — URLs already fetched in a previous run are skipped.
        # Uses Redis SyncBloomFilter when REDIS_URL is set, FileBloomFilter otherwise.
        _cross_run_dedup = get_sync_dedup(self.project_name, self.site_name)

        fetched_count = 0
        fetch_lock    = threading.Lock()
        # In-run dedup — catches duplicates within this single crawl run
        _seen_this_run: set[str] = set()

        def fetch_one(key: str) -> None:
            nonlocal fetched_count
            if not key:
                return

            url = key.split("|")[0]

            # In-run dedup (fast, in-process)
            with fetch_lock:
                if url in _seen_this_run:
                    logging.debug("In-run dedup: skipping %s", url)
                    return
                _seen_this_run.add(url)

            # Fix 7: cross-run dedup (Redis / file persisted across runs)
            try:
                if _cross_run_dedup.seen_sync(url):
                    logging.debug("Cross-run dedup: skipping already-fetched %s", url)
                    return
            except Exception:
                pass  # dedup failure is non-fatal; fetch anyway

            # Per-domain rate limiting
            try:
                domain = urlparse(url).netloc or url
                _rate_limiter.acquire(domain)
            except Exception:
                sleep(FETCH_SLEEP_SEC)

            result = sdfFetch.get_page_content_hash(
                url,
                proxy=proxy or None,
                extended_header=extended_header or None,
                max_retries=max_retries,
                timeout=timeout,
            )

            output_file = str(output_dir / f"{formatted_dt}{sdfFetch.encode(key)}.html")
            data = {"url": key, "output_file": output_file}

            if result["status_code"] == 200:
                content = result["page_doc"]
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                with open(output_file, "wb") as f:
                    f.write(content_bytes)
                sdfFetch.print_info_message("success", f"Fetched: {url}")
                # Mark as seen in cross-run dedup only on success
                try:
                    _cross_run_dedup.add_sync(url)
                except Exception:
                    pass
                with fetch_lock:
                    fetched_count += 1
                    crawl_status.update_progress(
                        self.project_name, self.site_name, schedule_key,
                        retriever_fetched=fetched_count,
                    )
            else:
                sdfFetch.print_error_message("error", f"Failed ({result['status_code']}): {url}")

            # Write metadata regardless of success so parser can log partial runs
            with fetch_lock:
                with open(metadata_file, "a", encoding="utf-8") as f:
                    f.write(str(data) + "\n")

        keys = [k for k in output_queue if k]
        if keys:
            n_workers = min(NUM_FETCH_WORKERS, len(keys))
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = {executor.submit(fetch_one, k): k for k in keys}
                for fut in as_completed(futures):
                    try:
                        fut.result(timeout=300)
                    except FuturesTimeoutError:
                        logging.error("Worker timed out for %s", futures[fut])
                    except Exception:
                        logging.exception("Worker failed for %s", futures[fut])

        sdfFetch.print_info_message(
            "success",
            f"[retriever] Completed schedule_id={schedule_key} | "
            f"Fetched: {fetched_count}/{len(output_queue)}",
        )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_retriever.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir      = Path(__file__).resolve().parent.parent
    project_name  = sys.argv[1]
    site_name     = sys.argv[2]
    schedule_key  = sys.argv[3]
    url_retriever = UrlRetriever(base_dir, project_name, site_name)
    url_retriever.main(schedule_key)
