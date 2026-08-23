"""
run_direct_crawl.py — queueless single-site crawl (discovery -> fetch -> parse).

The normal pipeline hands URLs from discovery to the retriever via a RabbitMQ
queue. When the broker is unreachable (or you just want a quick one-off run
without infra), this collects discovered URLs in-process instead of publishing
them, fetches them directly, and writes output in the exact same layout
url_retriever.py would — so UrlParser (which never touched RabbitMQ) runs
completely unchanged.

Usage:
    python run_direct_crawl.py <project> <site> <schedule_id>

Example:
    python run_direct_crawl.py media_crawl fashion_united_global_com direct001
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import yaml

from sdf_module.url_discovery import UrlDiscovery
from sdf_module.url_parser import UrlParser
from sdf_module.sdf_fetch import sdfFetch, disable_proxy
from config.settings import settings as _settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


class _DirectDiscovery(UrlDiscovery):
    """UrlDiscovery that collects discovered URLs in memory instead of
    publishing them to RabbitMQ — everything else (threaded depth-walking,
    per-site pagination/product methods) is reused unchanged."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.collected_urls: list[str] = []

    def push_urls_to_queue(self, result_url: list[str], schedule_key: str) -> None:
        self.collected_urls.extend(result_url)


def _discover(project: str, site: str, schedule_key: str) -> list[str]:
    disc = _DirectDiscovery(BASE_DIR, project, site)
    disc.output_dir = BASE_DIR / f"scrape_output/discovery_output/{project}"
    disc.output_dir.mkdir(parents=True, exist_ok=True)
    disc.collector_dir = BASE_DIR / f"url_discovery/{project}"
    (disc.output_dir / f"{site}_{project}_{schedule_key}.txt").write_text("")
    disc.main_execution(schedule_key)
    return disc.collected_urls


def _retrieve(project: str, site: str, schedule_key: str, urls: list[str]) -> tuple[int, int]:
    """Fetch each URL directly (no queue) and write HTML + metadata in the
    same layout url_retriever.py uses, so UrlParser can consume it as-is."""
    yaml_file_path = BASE_DIR / "url_discovery" / project / f"{site}_{project}.yml"
    with open(yaml_file_path, "r", encoding="utf-8") as f:
        yaml_content = yaml.safe_load(f) or {}
    request_params  = yaml_content.get("request_params", {})
    extended_header = request_params.get("extended_header")
    max_retries     = request_params.get("max_retries", 3)
    timeout         = request_params.get("timeout", 30)
    proxy           = request_params.get("proxy")

    formatted_dt = date.today().strftime("%Y%m%d")
    output_dir = (
        BASE_DIR / "scrape_output" / "retriever_output" / project
        / f"{site}_{project}" / schedule_key
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = output_dir / f"{schedule_key}_queue.txt"

    fetch_lock = threading.Lock()
    fetched = failed = 0
    metadata_fh = open(metadata_file, "a", encoding="utf-8")

    def fetch_one(url: str) -> None:
        nonlocal fetched, failed
        result = sdfFetch.get_page_content_hash(
            url,
            proxy=proxy or None,
            extended_header=extended_header or None,
            max_retries=max_retries,
            timeout=timeout,
        )
        output_file = str(output_dir / f"{formatted_dt}{sdfFetch.encode(url)}.html")
        data = {"url": url, "output_file": output_file}

        if result["status_code"] == 200:
            content_bytes = (
                result["page_doc"].encode("utf-8")
                if isinstance(result["page_doc"], str)
                else result["page_doc"]
            )
            with open(output_file, "wb") as fh:
                fh.write(content_bytes)
            with fetch_lock:
                fetched += 1
        else:
            with fetch_lock:
                failed += 1

        with fetch_lock:
            metadata_fh.write(json.dumps(data) + "\n")
            metadata_fh.flush()

    try:
        n_workers = min(_settings.NUM_FETCH_WORKERS, len(urls)) or 1
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futs = [executor.submit(fetch_one, u) for u in urls]
            for fut in as_completed(futs):
                try:
                    fut.result(timeout=300)
                except Exception:
                    logger.exception("[%s/%s] Fetch worker failed", project, site)
    finally:
        metadata_fh.close()

    logger.info(
        "[%s/%s] Fetched=%d Failed=%d Total=%d", project, site, fetched, failed, len(urls)
    )
    return fetched, failed


def run(project: str, site: str, schedule_id: str) -> dict:
    """Run discovery -> fetch -> parse for one site. Returns a summary dict."""
    summary = {"project": project, "site": site, "schedule_id": schedule_id}

    logger.info("=== %s/%s : discovery ===", project, site)
    urls = _discover(project, site, schedule_id)
    summary["discovered"] = len(urls)
    logger.info("[%s/%s] Discovered %d URLs", project, site, len(urls))
    if not urls:
        summary["status"] = "no_urls"
        return summary

    logger.info("=== %s/%s : fetch (%d URLs) ===", project, site, len(urls))
    fetched, failed = _retrieve(project, site, schedule_id, urls)
    summary["fetched"] = fetched
    summary["failed"]  = failed

    logger.info("=== %s/%s : parse ===", project, site)
    UrlParser(BASE_DIR, project, site).main(schedule_id)

    csv_path = (
        BASE_DIR / "scrape_output" / "parser_output" / project
        / f"{site}_{project}_{schedule_id}" / f"{site}_{project}.csv"
    )
    summary["csv_path"] = str(csv_path) if csv_path.exists() else None
    summary["status"] = "completed"
    return summary


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python run_direct_crawl.py <project> <site> <schedule_id>")
        sys.exit(1)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    disable_proxy()   # Webshare account is out of credit — fetch direct instead
    result = run(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
