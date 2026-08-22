from .sdf_fetch import *
from . import crawl_status
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, List
from config.settings import settings as _settings

NUM_DISCOVERY_WORKERS = _settings.NUM_DISCOVERY_WORKERS
_WORKER_TIMEOUT_SEC   = 60


class UrlDiscovery:
    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlDiscovery for project: {project_name} and site: {site_name}",
        )
        self.base_dir      = base_dir
        self.output_dir    = ""
        self.collector_dir = ""
        self.project_name  = project_name
        self.site_name     = site_name

    def push_urls_to_queue(self, result_url: List[str], schedule_key: str) -> None:
        if not result_url:
            return
        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        sdfFetch.print_info_message(
            "info",
            f"Pushing {len(result_url)} URLs to RabbitMQ for {self.project_name}/{self.site_name}",
        )
        connection = None
        try:
            connection, channel = sdfFetch.get_rabbitmq_channel()
            channel.queue_declare(queue=queue_name, durable=True)
            for url in result_url:
                channel.basic_publish(
                    exchange="",
                    routing_key=queue_name,
                    body=url.encode(),
                    properties=pika.BasicProperties(delivery_mode=2),
                )
            sdfFetch.print_info_message("success", f"Pushed {len(result_url)} URLs to queue {queue_name}")
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

    def get_urls_by_depth(
        self,
        urls: List[str],
        depth: dict,
        module_instance: Any,
        schedule_key: str,
    ) -> int:
        if not urls:
            sdfFetch.print_error_message("error", "No seed URLs provided for discovery stage.")
            return 0

        depth_items = sorted(
            (
                (int(key.replace("depth", "")), value)
                for key, value in depth.items()
                if key.startswith("depth") and key != "depth0"
            ),
            key=lambda item: item[0],
        )

        pending_urls = list(urls)
        discovered_count = 0
        for current_level, current_depth in depth_items:
            if not isinstance(current_depth, dict):
                continue
            method_name = current_depth.get("method_name")
            if not method_name:
                sdfFetch.print_error_message(
                    "error", f"Missing method_name for depth level {current_level}."
                )
                return discovered_count

            method_to_call = getattr(module_instance, method_name, None)
            if not callable(method_to_call):
                logging.warning("No method '%s' found on %s", method_name, module_instance)
                return discovered_count

            sdfFetch.print_info_message(
                "info",
                f"[discovery] depth{current_level}: {len(pending_urls)} URLs | method={method_name}",
            )

            next_urls: List[str] = []
            next_lock = threading.Lock()

            def _fetch_url(url: str) -> None:
                try:
                    result_url = method_to_call(url, depth, current_level)
                    if isinstance(result_url, str):
                        result_url = [result_url]
                    elif result_url is None:
                        result_url = []
                    with next_lock:
                        next_urls.extend(result_url)
                except Exception as e:
                    sdfFetch.print_error_message("error", f"URL fetching failed for {url}: {e}")

            n_workers = min(NUM_DISCOVERY_WORKERS, len(pending_urls))
            if n_workers == 0:
                sdfFetch.print_info_message("info", f"[discovery] depth{current_level}: no URLs to process, skipping")
                pending_urls = []
                continue
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futs = {executor.submit(_fetch_url, url): url for url in pending_urls}
                for fut in as_completed(futs):
                    try:
                        fut.result(timeout=_WORKER_TIMEOUT_SEC)
                    except Exception:
                        logging.exception("Discovery worker failed for %s", futs[fut])

            sdfFetch.print_info_message(
                "info",
                f"[discovery] depth{current_level} complete: {len(next_urls)} URLs found",
            )

            if current_level == depth_items[-1][0]:
                self.push_urls_to_queue(next_urls, schedule_key)
                discovered_count += len(next_urls)

            pending_urls = next_urls

        return discovered_count

    def main_execution(self, schedule_key: str) -> int:
        sdfFetch.print_info_message(
            "info", f"Starting main execution for {self.project_name}/{self.site_name}"
        )
        try:
            yaml_file_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.yml"
            with open(yaml_file_path, "r", encoding="utf-8") as f:
                depth = yaml.safe_load(f) or {}

            module_path = Path(self.collector_dir) / f"{self.site_name}_{self.project_name}.py"
            class_name  = normalize_class_name(self.project_name, self.site_name)

            try:
                spec   = importlib.util.spec_from_file_location(class_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                site_instance = getattr(module, class_name)()
            except Exception as e:
                sdfFetch.print_error_message("error", f"Error importing module from {module_path}: {e}")
                return 0

            seed_url = depth.get("depth0", {}).get("seed_url")
            if not seed_url:
                sdfFetch.print_error_message("error", "depth0.seed_url is missing or empty.")
                return 0

            return self.get_urls_by_depth(seed_url, depth, site_instance, schedule_key)

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
            raise

    def main(self, schedule_key: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"[discovery] Starting for project={self.project_name}, "
            f"site={self.site_name}, schedule_id={schedule_key}",
        )
        self.output_dir    = Path(self.base_dir) / f"scrape_output/discovery_output/{self.project_name}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.collector_dir = Path(self.base_dir) / f"url_discovery/{self.project_name}"

        filepath = self.output_dir / f"{self.site_name}_{self.project_name}_{schedule_key}.txt"
        filepath.write_text("")

        discovered_count = self.main_execution(schedule_key)
        crawl_status.update_progress(
            self.project_name, self.site_name, schedule_key,
            stage="discovery", discovery_urls=discovered_count,
        )
        sdfFetch.print_info_message(
            "success",
            f"[discovery] Completed schedule_id={schedule_key} | URLs discovered: {discovered_count}",
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
