from .sdf_fetch import *

class UrlParser:
    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message("info", f"Initializing UrlParser for project: {project_name} and site: {site_name}")
        self.base_dir = base_dir
        self.project_name = project_name
        self.site_name = site_name
        self.parser_dir = Path(base_dir) / "url_data_parser"
        self.count = 0

    def extract_records(self, output, page_doc, config, site_instance):
        sdfFetch.print_info_message("info", f"Extracting records for project: {self.project_name} and site: {self.site_name}")
        """
        Modify and extract multiple records from the page_doc using site-specific methods.
        Args:
            page_doc: Parsed document for the fetched page.
            config: Field extraction rules from the YAML configuration.
            site_instance: Instance of the site-specific class.
        Returns:
            List of extracted records.
        """
        # Use the site-specific method to modify the page_doc
        subsections = site_instance.modify_page_doc(output, page_doc)
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
                        # Call the respective extraction method with the sub_doc and field rules
                        record[field] = extraction_method(sub_doc, output)
                    except Exception as e:
                        record[field] = None
                        logging.warning(f"Error extracting field {field}: {e}")
                else:
                    logging.warning(f"Method {method_name} not implemented for field {field}.")
            records.append(record)
        sdfFetch.print_info_message("success", f"Records extracted successfully for project: {self.project_name} and site: {self.site_name}")
        return records

    def main(self, schedule_key):
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
            
            with open(yaml_file_path, 'r') as file:
                config = yaml.safe_load(file)  # Load the configuration from the YAML file

            module_path = self.parser_dir / f"{self.project_name}/{self.site_name}_{self.project_name}.py"
            class_name_in_site_script = f"{self.site_name}_{self.project_name}"
            class_name_in_site_script = ''.join([word.capitalize() for word in class_name_in_site_script.split('_')])
            try:
                spec = importlib.util.spec_from_file_location(class_name_in_site_script, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                SiteClass = getattr(module, class_name_in_site_script)
                site_instance = SiteClass()
            except Exception as e:
                sdfFetch.print_error_message("error", f"Error importing module from {module_path}: {e}")
                return

            # Fetching file paths (where URLs are stored)
            output_queue = Path(self.base_dir) / f"scrape_output/retriever_output/{self.project_name}/{self.site_name}_{self.project_name}/{schedule_key}/{schedule_key}_queue.txt"
            with open(output_queue, 'r') as file:
                file_paths = [line.strip() for line in file.readlines()]

            sdfFetch.print_info_message(
                "info",
                f"[parser] Processing {len(file_paths)} pages for schedule_id={schedule_key}"
            )

            total_records = 0
            for output in file_paths:
                output_key = eval(output)
                output = output_key.get("output_file")
                with open(output, 'r', encoding='utf-8') as file:
                    page_content = file.read()
                page_doc = etree.HTML(page_content)
                extracted_data = self.extract_records(output_key.get("url"), page_doc, config, site_instance)
                total_records += len(extracted_data)
                output_file = Path(self.base_dir) / f"scrape_output/parser_output/{self.project_name}/{self.site_name}_{self.project_name}_{schedule_key}"
                output_file.mkdir(parents=True, exist_ok=True)
                output_file = output_file / f"{self.site_name}_{self.project_name}.csv"

                with open(output_file, mode='a', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=config['fields'].keys())
                    if file.tell() == 0:
                        writer.writeheader()
                    writer.writerows(extracted_data)

            sdfFetch.print_info_message(
                "success",
                f"[parser] Completed schedule_id={schedule_key} | Records extracted: {total_records} from {len(file_paths)} pages"
            )

        except Exception as e:
            sdfFetch.print_error_message("error", f"Unhandled error during execution: {e}")
            logging.exception("Unhandled error during execution")
            raise

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_retriever.py <project_name> <site_name>")
        sys.exit(1)
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    schedule_key = sys.argv[3]
    url_parser = UrlParser(base_dir,project_name,site_name)
    url_parser.main(schedule_key)