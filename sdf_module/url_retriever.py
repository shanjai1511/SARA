from .sdf_fetch import *

class UrlRetriever:

    def __init__(self, base_dir, project_name, site_name):
        sdfFetch.print_info_message("info", f"Initializing UrlRetriever for project: {project_name} and site: {site_name}")
        self.base_dir = base_dir
        self.output_dir = ""
        self.project_name = project_name
        self.site_name = site_name

    def fetch_retriever_output(self, schedule_key):
        sdfFetch.print_info_message(
            "info",
            f"Fetching discovery_output for project: {self.project_name} and site: {self.site_name}"
        )

        urls = []

        try:
            queue_name = f"{self.site_name}_{self.project_name}_{schedule_key}_queue"
            connection, channel = sdfFetch.get_rabbitmq_channel()

            channel.queue_declare(queue=queue_name, durable=True)

            MAX_URLS = 2

            for _ in range(MAX_URLS):
                method, properties, body = channel.basic_get(queue=queue_name)

                if body is None:
                    # queue empty
                    break

                url = body.decode()
                urls.append(url)

                # acknowledge → remove from queue
                channel.basic_ack(delivery_tag=method.delivery_tag)

            connection.close()

        except Exception as e:
            sdfFetch.print_error_message("error", str(e))
            logging.exception("RabbitMQ fetch failed")

        return urls


    def main(self,schedule_key):
        sdfFetch.print_info_message("info", f"Starting script execution of url_retriever for project: {self.project_name} and site: {self.site_name}")
        yaml_file_path = Path(self.base_dir) / f"url_discovery/{self.project_name}/{self.site_name}_{self.project_name}.yml"
        sdfFetch.print_info_message("info", f"Loading configuration file: {yaml_file_path}")
        with open(yaml_file_path, 'r') as file:
            yaml_content = yaml.safe_load(file)

        extended_header = yaml_content.get("request_params", {}).get("extended_header", {})
        output_queue = self.fetch_retriever_output(schedule_key)
        today = date.today()
        formatted_date = today.strftime('%Y%m%d')
        output_dir = Path(self.base_dir) / f"scrape_output/retriever_output/{self.project_name}/{self.site_name}_{self.project_name}/{schedule_key}/"
        output_dir.mkdir(parents=True, exist_ok=True)

        #output_queue = Path(self.base_dir) / f"scrape_output/retriever_output/{schedule_key}/{self.project_name}/{self.site_name}_{self.project_name}.txt"
        
        for key in output_queue:
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
            
            metadata_file = output_dir / f"{schedule_key}_queue.txt"
            with open(metadata_file, "a") as file:
                file.write(str(data) + "\n")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_retriever.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    schedule_key = sys.argv[3]
    url_retriever = UrlRetriever(base_dir,project_name,site_name)
    url_retriever.main(schedule_key)