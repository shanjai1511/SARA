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

_rate_limiter = SyncDomainRateLimiter()

# Configurable via env vars (see .env.example)
NUM_FETCH_WORKERS = _settings.NUM_FETCH_WORKERS
FETCH_SLEEP_SEC = _settings.FETCH_SLEEP_SEC

class UrlRetriever:

    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlRetriever for project: {project_name} and site: {site_name}",
        )
        self.base_dir = base_dir
        self.output_dir = ""
        self.project_name = project_name
        self.site_name = site_name

    def fetch_retriever_output(self, schedule_key: str) -> List[str]:
        sdfFetch.print_info_message(
            "info",
            f"Fetching discovery_output for project: {self.project_name} and site: {self.site_name}",
        )

        urls: List[str] = []
        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        connection = None

        try:
            connection, channel = sdfFetch.get_rabbitmq_channel()
            channel.queue_declare(queue=queue_name, durable=True)

            MAX_URLS = _settings.MAX_URLS
            for _ in range(MAX_URLS):
                method, properties, body = channel.basic_get(queue=queue_name)
                if body is None:  # queue empty
                    break
                url = body.decode()
                urls.append(url)
                channel.basic_ack(delivery_tag=method.delivery_tag)
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
            f"[retriever] Starting for project={self.project_name}, site={self.site_name}, schedule_id={schedule_key}"
        )
        yaml_file_path = Path(self.base_dir) / "url_discovery" / self.project_name / f"{self.site_name}_{self.project_name}.yml"
        sdfFetch.print_info_message("info", f"Loading configuration file: {yaml_file_path}")
        try:
            with open(yaml_file_path, "r", encoding="utf-8") as file:
                yaml_content = yaml.safe_load(file) or {}
        except FileNotFoundError:
            sdfFetch.print_error_message(
                "error",
                f"Retriever YAML configuration not found: {yaml_file_path}",
            )
            return

        request_params = yaml_content.get("request_params", {})
        extended_header = request_params.get("extended_header")
        max_retries = request_params.get("max_retries", 3)
        timeout = request_params.get("timeout", 30)

        output_queue = self.fetch_retriever_output(schedule_key)
        total_urls = len(output_queue)
        crawl_status.update_progress(
            self.project_name, self.site_name, schedule_key,
            stage="retriever", retriever_total=total_urls, retriever_fetched=0,
        )
        sdfFetch.print_info_message(
            "info",
            f"[retriever] Fetched {total_urls} URLs from queue for schedule_id={schedule_key}",
        )

        today = date.today()
        formatted_date = today.strftime("%Y%m%d")
        output_dir = (
            Path(self.base_dir)
            / "scrape_output"
            / "retriever_output"
            / self.project_name
            / f"{self.site_name}_{self.project_name}"
            / schedule_key
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata_file = output_dir / f"{schedule_key}_queue.txt"

        fetched_count = 0
        fetch_lock = threading.Lock()

        def fetch_one(key):
            nonlocal fetched_count
            if not key:
                return
            url = key.split("|")[0]
            # Per-domain rate limiting (replaces fixed sleep)
            try:
                domain = urlparse(url).netloc or url
                _rate_limiter.acquire(domain)
            except Exception:
                sleep(FETCH_SLEEP_SEC)  # fallback if URL parse fails
            result = sdfFetch.get_page_content_hash(
                url,
                extended_header=extended_header or None,
                max_retries=max_retries,
                timeout=timeout,
            )
            data = {"url": key, "output_file": str(output_dir / f"{formatted_date}{sdfFetch.encode(key)}.html")}
            if result["status_code"] == 200:
                page_content = result["page_doc"]
                content_bytes = page_content.encode("utf-8") if isinstance(page_content, str) else page_content
                with open(data["output_file"], "wb") as f:
                    f.write(content_bytes)
                sdfFetch.print_info_message("success", f"Successfully fetched page content for URL: {url}")
                with fetch_lock:
                    fetched_count += 1
                    crawl_status.update_progress(
                        self.project_name, self.site_name, schedule_key,
                        retriever_fetched=fetched_count
                    )
            else:
                sdfFetch.print_error_message("error", f"Failed to fetch page content for URL: {url}")
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
                        fut.result(timeout=300)  # 5-minute hard cap per URL fetch
                    except FuturesTimeoutError:
                        logging.error("Worker timed out for %s", futures[fut])
                    except Exception as exc:
                        logging.exception("Worker failed for %s", futures[fut])

        sdfFetch.print_info_message(
            "success",
            f"[retriever] Completed schedule_id={schedule_key} | Pages fetched: {fetched_count}/{len(output_queue)}"
        )

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_retriever.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir = Path(__file__).resolve().parent.parent
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    schedule_key = sys.argv[3]
    url_retriever = UrlRetriever(base_dir, project_name, site_name)
    url_retriever.main(schedule_key)
