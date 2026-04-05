from .sdf_fetch import *
from . import crawl_status
from concurrent.futures import ThreadPoolExecutor, as_completed
import ast
import threading
from typing import Any, Dict, List

from config.settings import settings as _settings

# Configurable via NUM_PARSE_WORKERS env var (default: 4)
NUM_PARSE_WORKERS = _settings.NUM_PARSE_WORKERS


class UrlParser:
    def __init__(self, base_dir: str | Path, project_name: str, site_name: str) -> None:
        sdfFetch.print_info_message(
            "info",
            f"Initializing UrlParser for project: {project_name} and site: {site_name}",
        )
        self.base_dir = base_dir
        self.project_name = project_name
        self.site_name = site_name
        self.parser_dir = Path(base_dir) / "url_data_parser"
        self.count = 0

    def extract_records(self, output, page_doc, config, site_instance):
        """
        Modify and extract multiple records from the page_doc using site-specific methods.
        Args:
            output: URL key / metadata for the fetched page.
            page_doc: Parsed document for the fetched page.
            config: Field extraction rules from the YAML configuration.
            site_instance: Instance of the site-specific class.
        Returns:
            List of extracted records.
        """
        sdfFetch.print_info_message("info", f"Extracting records for project: {self.project_name} and site: {self.site_name}")
        # Use the site-specific method to modify the page_doc
        modify_method = getattr(site_instance, "modify_page_doc", None)
        if callable(modify_method):
            subsections = modify_method(output, page_doc)
        else:
            subsections = [page_doc]

        if not subsections:
            subsections = [page_doc]  # If no subsections, treat the whole page_doc as one record

        records = []
        for sub_doc in subsections:
            record = {}
            for field, rules in config['fields'].items():
                method_name = f"get_{field}"
                if hasattr(site_instance, method_name):
                    extraction_method = getattr(site_instance, method_name)
                    try:
                        record[field] = extraction_method(sub_doc, output)
                    except Exception as e:
                        record[field] = None
                        logging.error(
                            "Error extracting field '%s' for URL %s: %s",
                            field, output, e, exc_info=True,
                        )
                else:
                    logging.warning("Method %s not implemented for field %s.", method_name, field)
            records.append(record)
        sdfFetch.print_info_message("success", f"Records extracted successfully for project: {self.project_name} and site: {self.site_name}")
        return records

    def _process_batch(self, batch: list, config: dict, site_instance: Any) -> List[Dict]:
        """Process a batch of metadata lines; return list of record dicts (for threaded parse)."""
        records: List[Dict] = []
        for line in batch:
            # metadata lines are Python dicts written as strings; use literal_eval for safety
            output_key = ast.literal_eval(line)
            output_path = output_key.get("output_file")
            with open(output_path, "r", encoding="utf-8") as f:
                page_content = f.read()
            page_doc = etree.HTML(page_content)
            records.extend(
                self.extract_records(output_key.get("url"), page_doc, config, site_instance)
            )
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
            f"[parser] Starting for project={self.project_name}, site={self.site_name}, schedule_id={schedule_key}"
        )
        try:
            yaml_file_path = self.parser_dir / f"{self.project_name}/{self.site_name}_{self.project_name}.yml"
            sdfFetch.print_info_message("info", f"Loading configuration file: {yaml_file_path}")

            with open(yaml_file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file) or {}

            module_path = self.parser_dir / f"{self.project_name}/{self.site_name}_{self.project_name}.py"
            # derive class name using shared utility
            class_name_in_site_script = normalize_class_name(self.project_name, self.site_name)
            try:
                spec = importlib.util.spec_from_file_location(class_name_in_site_script, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                SiteClass = getattr(module, class_name_in_site_script)
                site_instance = SiteClass()
            except Exception as e:
                sdfFetch.print_error_message("error", f"Error importing module from {module_path}: {e}")
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
                    "error",
                    f"Retriever metadata file not found: {output_queue}",
                )
                return

            with open(output_queue, 'r', encoding='utf-8') as file:
                file_paths = [line.strip() for line in file.readlines() if line.strip()]

            total_pages = len(file_paths)
            if total_pages == 0:
                sdfFetch.print_info_message(
                    "info",
                    f"No pages to parse for schedule_id={schedule_key}.",
                )
                crawl_status.update_progress(
                    self.project_name, self.site_name, schedule_key,
                    stage="parser", parser_pages=0, parser_records=0
                )
                return

            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                stage="parser", parser_pages=total_pages, parser_records=0
            )
            sdfFetch.print_info_message(
                "info",
                f"[parser] Processing {total_pages} pages for schedule_id={schedule_key} (threaded)"
            )

            # Split into chunks for worker threads; each thread parses its segment
            n_workers = min(NUM_PARSE_WORKERS, total_pages) or 1
            chunk_size = (total_pages + n_workers - 1) // n_workers
            chunks = [file_paths[i: i + chunk_size] for i in range(0, total_pages, chunk_size)]

            # Streaming CSV: open file before pool so each batch is written to disk
            # immediately — avoids accumulating all records in memory (OOM on large crawls).
            output_dir = Path(self.base_dir) / f"scrape_output/parser_output/{self.project_name}/{self.site_name}_{self.project_name}_{schedule_key}"
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / f"{self.site_name}_{self.project_name}.csv"

            total_records = 0
            pages_done = 0
            csv_lock = threading.Lock()  # serialise writes from multiple threads

            with open(csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=config["fields"].keys())
                writer.writeheader()

                with ThreadPoolExecutor(max_workers=n_workers) as executor:
                    futures = {executor.submit(self._process_batch, ch, config, site_instance): len(ch) for ch in chunks}
                    for fut in as_completed(futures):
                        try:
                            records = fut.result(timeout=300)  # 5-minute hard cap per batch
                        except TimeoutError:
                            logging.error("Parser batch timed out")
                            pages_done += futures[fut]
                            continue
                        except Exception:
                            logging.exception("Batch processing failed")
                            pages_done += futures[fut]
                            continue

                        with csv_lock:
                            writer.writerows(records)
                            csv_file.flush()  # ensure data reaches disk progressively

                        total_records += len(records)
                        pages_done += futures[fut]
                        crawl_status.update_progress(
                            self.project_name,
                            self.site_name,
                            schedule_key,
                            parser_records=total_records,
                            parser_pages_done=min(pages_done, total_pages),
                        )

            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                parser_records=total_records, parser_pages_done=total_pages
            )
            sdfFetch.print_info_message(
                "success",
                f"[parser] Completed schedule_id={schedule_key} | Records extracted: {total_records} from {len(file_paths)} pages"
            )

            # Upload parsed CSV to Elasticsearch (no-op if ELASTICSEARCH_URL not set)
            try:
                from core.es_uploader import upload_csv
                es_count = upload_csv(csv_path, self.project_name, self.site_name, schedule_key)
                if es_count:
                    sdfFetch.print_info_message("success", f"[parser] Uploaded {es_count} docs to Elasticsearch")
            except Exception:
                logging.exception("ES upload step failed — crawl result is still saved locally")

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
            logging.exception("Unhandled error during execution")
            raise


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_parser.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    base_dir = Path(__file__).resolve().parent.parent
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    schedule_key = sys.argv[3]
    url_parser = UrlParser(base_dir, project_name, site_name)
    url_parser.main(schedule_key)
