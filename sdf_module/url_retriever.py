from sdf_fetch import *

class UrlRetriever:

    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message("info", f"Initializing UrlRetriever for project: {project_name} and site: {site_name}")
        self.base_dir = base_dir
        self.output_dir = ""
        self.project_name = project_name
        self.site_name = site_name

    def fetch_retriever_output(self):
        sdfFetch.print_info_message("info", f"Fetching discovery_output for project: {self.project_name} and site: {self.site_name}")
        urls = []
        try:
            self.output_dir = Path(self.base_dir) / f"scrape_output/discovery_output/{self.project_name}"
            filepath = self.output_dir / f"{self.site_name}_{self.project_name}.txt"

            with open(filepath, "r") as f:
                for url in f:
                    urls.append(url.strip())
        except FileNotFoundError as e:
            sdfFetch.print_error_message("error", f"File not found: {filepath}")
            logging.exception("File not found")
        return urls

    def main(self):
        sdfFetch.print_info_message("info", f"Starting script execution of url_retriever for project: {self.project_name} and site: {self.site_name}")
        yaml_file_path = Path(self.base_dir) / f"url_discovery/{self.project_name}/{self.site_name}_{self.project_name}.yml"
        sdfFetch.print_info_message("info", f"Loading configuration file: {yaml_file_path}")
        with open(yaml_file_path, 'r') as file:
            yaml_content = yaml.safe_load(file)

        extended_header = yaml_content.get("request_params", {}).get("extended_header", {})
        urls = self.fetch_retriever_output()
        today = date.today()
        formatted_date = today.strftime('%Y%m%d')
        output_dir = Path(self.base_dir) / f"scrape_output/retriever_output/{self.project_name}/{formatted_date}/{self.site_name}_{self.project_name}"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_queue = Path(self.base_dir) / f"scrape_output/retriever_output/{self.project_name}/{formatted_date}/{self.site_name}_{self.project_name}.txt"
        
        with open(output_queue, "a") as file:  # Open in append mode
            for key in urls:
                if not key:
                    continue
                url = key.split("|")[0]
                data = {}
                if extended_header:
                    result = sdfFetch.get_page_content_hash(url, extended_header)
                else:
                    result = sdfFetch.get_page_content_hash(url)
                data["url"] = key
                output_file = output_dir / f"{formatted_date}{sdfFetch.encode(key)}.html"
                data["output_file"] = str(output_file)
                
                if result["status_code"] == 200:
                    with open(output_file, "wb") as f:
                        f.write(result["page_doc"].encode("utf-8"))
                    sdfFetch.print_info_message("success", f"Successfully fetched page content for URL: {url}")
                else:
                    sdfFetch.print_error_message("error", f"Failed to fetch page content for URL: {url}")
                
                # Write the data to the file immediately
                file.write(str(data) + "\n")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python url_retriever.py <project_name> <site_name>")
        sys.exit(1)
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    url_retriever = UrlRetriever(base_dir,project_name,site_name)
    url_retriever.main()