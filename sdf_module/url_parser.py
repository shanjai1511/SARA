from .sdf_fetch import *
from . import crawl_status
from concurrent.futures import (
    ThreadPoolExecutor,
    wait as _fut_wait,
    FIRST_COMPLETED,
    TimeoutError as FuturesTimeoutError,
)
import threading
from typing import Any, Dict, Iterator, List
from config.settings import settings as _settings

NUM_PARSE_WORKERS = _settings.NUM_PARSE_WORKERS
_MAX_IN_FLIGHT    = NUM_PARSE_WORKERS * 4


def _iter_metadata_lines(path: Path) -> Iterator[str]:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield line


class UrlParser:
    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlParser for project: {project_name} and site: {site_name}",
        )
        self.base_dir     = base_dir
        self.project_name = project_name
        self.site_name    = site_name
        self.parser_dir   = Path(base_dir) / "url_data_parser"

    def extract_records(self, output, page_doc, config, site_instance) -> List[Dict]:
        modify_method = getattr(site_instance, "modify_page_doc", None)
        subsections = modify_method(output, page_doc) if callable(modify_method) else None
        if not subsections:
            subsections = [page_doc]

        records: List[Dict] = []
        for sub_doc in subsections:
            record: Dict = {}
            for field in config["fields"]:
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
        output_key  = json.loads(line)
        output_path = output_key.get("output_file")
        with open(output_path, "r", encoding="utf-8") as f:
            page_content = f.read()
        page_doc = etree.HTML(page_content)
        return self.extract_records(output_key.get("url"), page_doc, config, site_instance)

    def main(self, schedule_key: str) -> None:
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
                sdfFetch.print_error_message("error", f"Retriever metadata file not found: {output_queue}")
                return

            lines = list(_iter_metadata_lines(output_queue))
            if not lines:
                sdfFetch.print_info_message("info", "No pages to parse.")
                crawl_status.update_progress(
                    self.project_name, self.site_name, schedule_key,
                    stage="parser", parser_pages=0, parser_records=0,
                )
                return

            total_pages = len(lines)
            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                stage="parser", parser_pages=total_pages, parser_records=0,
            )
            sdfFetch.print_info_message(
                "info", f"[parser] {total_pages} pages to parse | workers={NUM_PARSE_WORKERS}"
            )

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

                with ThreadPoolExecutor(max_workers=NUM_PARSE_WORKERS) as executor:
                    pending: dict = {}

                    def _drain_one(timeout: float = 120) -> None:
                        nonlocal total_records, pages_done
                        done, _ = _fut_wait(pending, timeout=timeout, return_when=FIRST_COMPLETED)
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
                        total_records += len(records)
                        pages_done    += 1
                        if pages_done % 10 == 0:
                            crawl_status.update_progress(
                                self.project_name, self.site_name, schedule_key,
                                parser_records=total_records,
                                parser_pages_done=min(pages_done, total_pages),
                            )

                    for line in lines:
                        while len(pending) >= _MAX_IN_FLIGHT:
                            _drain_one()
                        fut = executor.submit(self._process_one, line, config, site_instance)
                        pending[fut] = line

                    while pending:
                        _drain_one()

            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                parser_records=total_records, parser_pages_done=total_pages,
            )

            try:
                from core.es_uploader import upload_csv as _es_upload
                _es_upload(csv_path, self.project_name, self.site_name, schedule_key)
                sdfFetch.print_info_message("success", "[parser] ES upload complete")
            except Exception:
                logging.debug("ES upload skipped or failed", exc_info=True)

            sdfFetch.print_info_message(
                "success",
                f"[parser] Completed schedule_id={schedule_key} | "
                f"Records: {total_records} from {total_pages} pages",
            )

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
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
