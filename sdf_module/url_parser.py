"""
URL Parser — SARA pipeline stage 3.

Scale improvements:
  - Bounded-futures pattern: never more than MAX_IN_FLIGHT futures submitted
    at once.  For 1M pages, this means O(MAX_IN_FLIGHT) not O(1M) Future
    objects in RAM simultaneously.
  - Metadata file is streamed line-by-line; never loaded entirely into memory.
  - Per-record Prometheus metrics via core.metrics.
  - One parser worker = one HTML file (peak RAM = NUM_PARSE_WORKERS × one lxml tree).
"""
from .sdf_fetch import *
from . import crawl_status
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
    wait as _fut_wait,
    FIRST_COMPLETED,
    TimeoutError as FuturesTimeoutError,
)
import ast
import itertools
import threading
from typing import Any, Dict, Iterator, List

from config.settings import settings as _settings
from core.metrics import metrics

NUM_PARSE_WORKERS = _settings.NUM_PARSE_WORKERS

# Bounded-futures: submit at most this many futures at once so RAM stays bounded.
# = workers × 4 is a good pipeline depth (keeps workers busy without excess memory).
_MAX_IN_FLIGHT = NUM_PARSE_WORKERS * 4


def _iter_metadata_lines(path: Path) -> Iterator[str]:
    """Stream the retriever metadata file one line at a time — never loads it all."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield line


class UrlParser:
    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlParser for project: {project_name} and site: {site_name}",
        )
        self.base_dir     = base_dir
        self.project_name = project_name
        self.site_name    = site_name
        self.parser_dir   = Path(base_dir) / "url_data_parser"
        self.count        = 0

    def extract_records(self, output, page_doc, config, site_instance) -> List[Dict]:
        modify_method = getattr(site_instance, "modify_page_doc", None)
        subsections = modify_method(output, page_doc) if callable(modify_method) else None
        if not subsections:
            subsections = [page_doc]

        records: List[Dict] = []
        for sub_doc in subsections:
            record: Dict = {}
            for field, rules in config["fields"].items():
                method_name = f"get_{field}"
                if hasattr(site_instance, method_name):
                    try:
                        record[field] = getattr(site_instance, method_name)(sub_doc, output)
                    except Exception as e:
                        record[field] = None
                        logging.error(
                            "Error extracting field '%s' for URL %s: %s",
                            field, output, e, exc_info=True,
                        )
                else:
                    logging.warning("Method %s not found for field %s.", method_name, field)
            records.append(record)
        return records

    def _process_one(self, line: str, config: dict, site_instance: Any) -> List[Dict]:
        """Process a single page: one task = one HTML file.
        Peak memory = NUM_PARSE_WORKERS × one lxml tree."""
        output_key  = ast.literal_eval(line)
        output_path = output_key.get("output_file")
        domain      = ""
        try:
            from urllib.parse import urlparse as _up
            raw_url = output_key.get("url", "")
            domain  = _up(raw_url.split("|")[0]).netloc or raw_url
        except Exception:
            pass

        with metrics.parse_timer(domain):
            with open(output_path, "r", encoding="utf-8") as f:
                page_content = f.read()
            page_doc = etree.HTML(page_content)
            records  = self.extract_records(output_key.get("url"), page_doc, config, site_instance)

        for _ in records:
            metrics.record_parsed(domain, self.project_name)

        return records

    def main(self, schedule_key: str) -> None:
        sdfFetch.set_crawl_context(
            stage="parser",
            schedule_id=schedule_key,
            project=self.project_name,
            site=self.site_name,
        )
        sdfFetch.print_info_message(
            "info",
            f"[parser] Starting for project={self.project_name}, "
            f"site={self.site_name}, schedule_id={schedule_key}",
        )
        try:
            yaml_file_path = (
                self.parser_dir
                / f"{self.project_name}/{self.site_name}_{self.project_name}.yml"
            )
            with open(yaml_file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            module_path = (
                self.parser_dir
                / f"{self.project_name}/{self.site_name}_{self.project_name}.py"
            )
            class_name = normalize_class_name(self.project_name, self.site_name)
            try:
                spec   = importlib.util.spec_from_file_location(class_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                site_instance = getattr(module, class_name)()
            except Exception as e:
                sdfFetch.print_error_message("error", f"Module import failed: {e}")
                logging.exception("Module import failed")
                return

            output_queue = (
                Path(self.base_dir)
                / "scrape_output"
                / "retriever_output"
                / self.project_name
                / f"{self.site_name}_{self.project_name}"
                / schedule_key
                / f"{schedule_key}_queue.txt"
            )
            if not output_queue.exists():
                sdfFetch.print_error_message(
                    "error", f"Retriever metadata file not found: {output_queue}"
                )
                return

            # Stream metadata file — never load all N-million lines into RAM
            line_stream = _iter_metadata_lines(output_queue)
            # Peek to detect empty without consuming
            try:
                first_line = next(line_stream)
            except StopIteration:
                sdfFetch.print_info_message("info", "No pages to parse.")
                crawl_status.update_progress(
                    self.project_name, self.site_name, schedule_key,
                    stage="parser", parser_pages=0, parser_records=0,
                )
                return

            line_stream = itertools.chain([first_line], line_stream)

            # Count total pages for progress reporting (requires one pass of the file)
            total_pages = sum(1 for _ in _iter_metadata_lines(output_queue))
            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                stage="parser", parser_pages=total_pages, parser_records=0,
            )
            sdfFetch.print_info_message(
                "info",
                f"[parser] {total_pages} pages to parse | workers={NUM_PARSE_WORKERS} "
                f"| max_in_flight={_MAX_IN_FLIGHT}",
            )

            # Output CSV
            output_dir = (
                Path(self.base_dir)
                / f"scrape_output/parser_output/{self.project_name}"
                / f"{self.site_name}_{self.project_name}_{schedule_key}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / f"{self.site_name}_{self.project_name}.csv"

            total_records = 0
            pages_done    = 0
            csv_lock      = threading.Lock()

            with open(csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=config["fields"].keys())
                writer.writeheader()

                # Bounded-futures pattern:
                #   Submit up to _MAX_IN_FLIGHT futures at once.
                #   When the pool is full, drain one completed future before
                #   submitting the next.  This keeps RAM at O(MAX_IN_FLIGHT)
                #   regardless of total_pages (critical for 1M+ pages).
                with ThreadPoolExecutor(max_workers=NUM_PARSE_WORKERS) as executor:
                    pending: dict = {}  # future → line

                    def _drain_one(timeout: float = 120) -> None:
                        """Wait for one completed future and write its records."""
                        nonlocal total_records, pages_done
                        done, _ = _fut_wait(
                            pending, timeout=timeout, return_when=FIRST_COMPLETED
                        )
                        if not done:
                            return
                        fut = next(iter(done))
                        line_ref = pending.pop(fut)
                        try:
                            records = fut.result(timeout=5)
                        except FuturesTimeoutError:
                            logging.error("Parser timeout on: %s", line_ref)
                            pages_done += 1
                            return
                        except Exception:
                            logging.exception("Parser error on: %s", line_ref)
                            pages_done += 1
                            return
                        with csv_lock:
                            writer.writerows(records)
                            csv_file.flush()
                        total_records += len(records)
                        pages_done    += 1
                        crawl_status.update_progress(
                            self.project_name, self.site_name, schedule_key,
                            parser_records=total_records,
                            parser_pages_done=min(pages_done, total_pages),
                        )

                    for line in line_stream:
                        # If at capacity, drain one future before submitting
                        while len(pending) >= _MAX_IN_FLIGHT:
                            _drain_one()

                        fut = executor.submit(self._process_one, line, config, site_instance)
                        pending[fut] = line

                    # Drain all remaining futures
                    while pending:
                        _drain_one()

            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                parser_records=total_records,
                parser_pages_done=total_pages,
            )

            # Fix 5: ES upload happens ONCE after the full CSV is written —
            # outside any lock, outside the thread pool.
            # Previously this ran inside the CSV write lock per batch, stalling
            # all parser threads whenever ES was slow.
            try:
                from core.es_uploader import upload_csv as _es_upload
                _es_upload(csv_path, self.project_name, self.site_name, schedule_key)
                sdfFetch.print_info_message(
                    "success", "[parser] ES upload complete (deferred post-parse)"
                )
            except Exception:
                logging.debug("ES upload skipped or failed", exc_info=True)

            sdfFetch.print_info_message(
                "success",
                f"[parser] Completed schedule_id={schedule_key} | "
                f"Records: {total_records} from {total_pages} pages",
            )

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
            logging.exception("Unhandled error during execution")
            raise


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_parser.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir     = Path(__file__).resolve().parent.parent
    project_name = sys.argv[1]
    site_name    = sys.argv[2]
    schedule_key = sys.argv[3]
    url_parser   = UrlParser(base_dir, project_name, site_name)
    url_parser.main(schedule_key)
