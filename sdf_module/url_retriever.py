from __future__ import annotations

from .sdf_fetch import *
from . import crawl_status
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import threading
import logging
from pathlib import Path
from config.settings import settings as _settings

NUM_FETCH_WORKERS = _settings.NUM_FETCH_WORKERS

_WINDOW_SIZE         = max(NUM_FETCH_WORKERS * 2, 20)
_QUEUE_EMPTY_RETRIES = 36
_QUEUE_POLL_SLEEP    = 5
_HEARTBEAT_SECONDS   = 600
_WORKER_TIMEOUT_SEC  = 300


class UrlRetriever:

    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlRetriever for project: {project_name} and site: {site_name}",
        )
        self.base_dir     = base_dir
        self.project_name = project_name
        self.site_name    = site_name

    def main(self, schedule_key: str) -> None:
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
            sdfFetch.print_error_message("error", f"Retriever YAML not found: {yaml_file_path}")
            return

        request_params  = yaml_content.get("request_params", {})
        extended_header = request_params.get("extended_header")
        max_retries     = request_params.get("max_retries", 3)
        timeout         = request_params.get("timeout", 30)
        proxy           = request_params.get("proxy")

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

        _seen_this_run: set[str] = set()
        fetched_count = 0
        failed_count  = 0
        fetch_lock    = threading.Lock()

        def fetch_one(url_key: str) -> bool:
            nonlocal fetched_count, failed_count

            if not url_key:
                return True

            url = url_key.split("|")[0]

            with fetch_lock:
                if url in _seen_this_run:
                    return True
                _seen_this_run.add(url)

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
                content_bytes = (
                    result["page_doc"].encode("utf-8")
                    if isinstance(result["page_doc"], str)
                    else result["page_doc"]
                )
                with open(output_file, "wb") as fh:
                    fh.write(content_bytes)
                with fetch_lock:
                    fetched_count += 1
                    crawl_status.update_progress(
                        self.project_name, self.site_name, schedule_key,
                        retriever_fetched=fetched_count,
                    )
                success = True
            else:
                logging.error("[retriever] Failed (%s): %s", result["status_code"], url)
                with fetch_lock:
                    failed_count += 1

            with fetch_lock:
                with open(metadata_file, "a", encoding="utf-8") as fh:
                    fh.write(str(data) + "\n")

            return success

        queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
        try:
            params = pika.URLParameters(CLOUDAMQP_URL)
            params.heartbeat = _HEARTBEAT_SECONDS
            connection = pika.BlockingConnection(params)
            channel    = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
        except Exception as exc:
            sdfFetch.print_error_message("error", f"RabbitMQ connect failed: {exc}")
            return

        try:
            q     = channel.queue_declare(queue=queue_name, durable=True, passive=True)
            depth = q.method.message_count
            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                stage="retriever", retriever_total=depth, retriever_fetched=0,
            )
            sdfFetch.print_info_message(
                "info",
                f"[retriever] Queue depth={depth} | window={_WINDOW_SIZE} | workers={NUM_FETCH_WORKERS}",
            )
        except Exception:
            pass

        empty_retries   = 0
        total_processed = 0

        try:
            while True:
                try:
                    connection.process_data_events(time_limit=0)
                except Exception:
                    pass

                window: list[tuple[int, str]] = []
                for _ in range(_WINDOW_SIZE):
                    try:
                        method, _props, body = channel.basic_get(queue=queue_name, auto_ack=False)
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
                            "[retriever] Queue empty after %d consecutive polls — done", empty_retries
                        )
                        break
                    sleep(_QUEUE_POLL_SLEEP)
                    continue
                empty_retries = 0

                results: list[tuple[int, bool]] = []
                results_lock = threading.Lock()

                def _process(delivery_tag: int, url_key: str) -> None:
                    ok = fetch_one(url_key)
                    with results_lock:
                        results.append((delivery_tag, ok))

                n_workers = min(NUM_FETCH_WORKERS, len(window))
                with ThreadPoolExecutor(max_workers=n_workers) as executor:
                    futs = [executor.submit(_process, dt, uk) for dt, uk in window]
                    for fut in as_completed(futs):
                        try:
                            fut.result(timeout=_WORKER_TIMEOUT_SEC)
                        except FuturesTimeoutError:
                            logging.error("Worker timed out (window item)")
                        except Exception:
                            logging.exception("Worker raised in window")

                for delivery_tag, success in results:
                    try:
                        if success:
                            channel.basic_ack(delivery_tag=delivery_tag)
                        else:
                            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                    except Exception as exc:
                        logging.warning("ACK/NACK failed for tag=%d: %s", delivery_tag, exc)

                total_processed += len(window)
                logging.info(
                    "[retriever] Window complete | window=%d total=%d fetched=%d failed=%d",
                    len(window), total_processed, fetched_count, failed_count,
                )

        finally:
            try:
                channel.queue_delete(queue=queue_name)
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

        sdfFetch.print_info_message(
            "success",
            f"[retriever] Completed schedule_id={schedule_key} | "
            f"Fetched={fetched_count} Failed={failed_count} Total={total_processed}",
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
