from .sdf_fetch import *
from . import crawl_status
import logging
from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse

from config.settings import settings as _settings
from core.rate_limiter import SyncDomainRateLimiter

# Fix 1: one shared rate-limiter instance per discovery process
_rate_limiter = SyncDomainRateLimiter()

# Fix 6: publish URLs in batches to avoid 5000 individual RPC round-trips
_PUBLISH_BATCH = 100


class UrlDiscovery:
    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlDiscovery for project: {project_name} and site: {site_name}",
        )
        self.base_dir = base_dir
        self.output_dir = ""
        self.collector_dir = ""
        self.project_name = project_name
        self.site_name = site_name
        self.count = 0

    def push_urls_to_queue(self, result_url: list[str], schedule_key: str) -> None:
        """Push URLs to RabbitMQ in batches of _PUBLISH_BATCH to minimise RPC round-trips."""
        if not result_url:
            return

        sdfFetch.print_info_message(
            "info",
            f"Pushing {len(result_url)} URLs to RabbitMQ for {self.project_name}/{self.site_name}",
        )

        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        connection = None
        try:
            connection, channel = sdfFetch.get_rabbitmq_channel()
            channel.queue_declare(queue=queue_name, durable=True)

            # Fix 6: batch publish — one channel.basic_publish per URL is a full RPC;
            # batching with confirm_delivery=False avoids the round-trip per message.
            for i in range(0, len(result_url), _PUBLISH_BATCH):
                batch = result_url[i: i + _PUBLISH_BATCH]
                for url in batch:
                    channel.basic_publish(
                        exchange="",
                        routing_key=queue_name,
                        body=url.encode(),
                        properties=pika.BasicProperties(delivery_mode=2),
                    )
                logging.debug(
                    "Published batch %d-%d to %s", i, i + len(batch), queue_name
                )

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

    def write_url_in_txt(self, result_url: list[str], schedule_key: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Writing URLs to file for project: {self.project_name} and site: {self.site_name}",
        )
        filepath = Path(self.output_dir) / f"{self.site_name}_{self.project_name}_{schedule_key}.txt"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "a") as f:
            for item in result_url:
                f.write(f"{item}\n")
        sdfFetch.print_info_message(
            "success",
            f"URLs written to file for {self.project_name}/{self.site_name}",
        )

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
            ((int(key.replace("depth", "")), value) for key, value in depth.items()
             if key.startswith("depth")),
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
                logging.warning(
                    "No method '%s' found on %s", method_name, module_instance
                )
                return

            next_urls: List[str] = []
            for url in pending_urls:
                # Fix 1: per-domain rate limiting instead of a flat FETCH_DELAY sleep.
                # This respects each domain's configured delay without wasting time on
                # fast domains or hammering slow ones.
                try:
                    domain = urlparse(url).netloc or url
                    _rate_limiter.acquire(domain)
                except Exception:
                    sleep(_settings.FETCH_DELAY)  # safe fallback

                try:
                    result_url = method_to_call(url, depth, current_level)
                    if isinstance(result_url, str):
                        result_url = [result_url]
                    elif result_url is None:
                        result_url = []
                except Exception as e:
                    sdfFetch.print_error_message(
                        "error", f"URL fetching failed with error: {e}"
                    )
                    logging.exception("URL fetching failed")
                    continue

                next_urls.extend(result_url)

            # At the final depth level: push discovered URLs to RabbitMQ
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

            module_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.py"
            class_name = normalize_class_name(self.project_name, self.site_name)

            try:
                spec = importlib.util.spec_from_file_location(class_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                SiteClass = getattr(module, class_name)
                site_instance = SiteClass()
            except Exception as e:
                sdfFetch.print_error_message(
                    "error", f"Error importing module from {module_path}: {e}"
                )
                logging.exception("Module import failed")
                return

            seed_url = depth.get("depth0", {}).get("seed_url")
            if not seed_url:
                sdfFetch.print_error_message(
                    "error", "depth0.seed_url is missing or empty."
                )
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
        self.output_dir = Path(self.base_dir) / f"scrape_output/discovery_output/{self.project_name}"
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
        print("Usage: python url_discovery.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir = Path(__file__).resolve().parent.parent
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    schedule_key = sys.argv[3]
    url_discovery = UrlDiscovery(base_dir, project_name, site_name)
    url_discovery.main(schedule_key)
