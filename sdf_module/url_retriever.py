from .sdf_fetch import *
from . import crawl_status

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

            MAX_URLS = 500

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


    def main(self, schedule_key):
        sdfFetch.set_crawl_context(
            stage="retriever",
            schedule_id=schedule_key,
            project=self.project_name,
            site=self.site_name,
        )
        sdfFetch.print_info_message(
            "info",
            f"[retriever] Starting for project={self.project_name}, site={self.site_name}, schedule_id={schedule_key}"
        )
        yaml_file_path = Path(self.base_dir) / f"url_discovery/{self.project_name}/{self.site_name}_{self.project_name}.yml"
        sdfFetch.print_info_message("info", f"Loading configuration file: {yaml_file_path}")
        with open(yaml_file_path, 'r') as file:
            yaml_content = yaml.safe_load(file)

        request_params = yaml_content.get("request_params", {})
        extended_header = request_params.get("extended_header", {})
        max_retries = request_params.get("max_retries", 3)
        timeout = request_params.get("timeout", 30)
        output_queue = self.fetch_retriever_output(schedule_key)
        total_urls = len(output_queue)
        crawl_status.update_progress(
            self.project_name, self.site_name, schedule_key,
            stage="retriever", retriever_total=total_urls, retriever_fetched=0
        )
        sdfFetch.print_info_message(
            "info",
            f"[retriever] Fetched {total_urls} URLs from queue for schedule_id={schedule_key}"
        )
        today = date.today()
        formatted_date = today.strftime('%Y%m%d')
        output_dir = Path(self.base_dir) / f"scrape_output/retriever_output/{self.project_name}/{self.site_name}_{self.project_name}/{schedule_key}/"
        output_dir.mkdir(parents=True, exist_ok=True)

        fetched_count = 0
        for key in output_queue:
            if not key:
                continue
            url = key.split("|")[0]
            data = {}
            sleep(10)  # Sleep before each request to avoid overwhelming the server
            result = sdfFetch.get_page_content_hash(
                url,
                extended_header=extended_header or None,
                max_retries=max_retries,
                timeout=timeout,
            )
            data["url"] = key
            output_file = output_dir / f"{formatted_date}{sdfFetch.encode(key)}.html"
            data["output_file"] = str(output_file)            
            if result["status_code"] == 200:
                fetched_count += 1
                page_content = result["page_doc"]
                content_bytes = page_content.encode("utf-8") if isinstance(page_content, str) else page_content
                with open(output_file, "wb") as f:
                    f.write(content_bytes)
                sdfFetch.print_info_message("success", f"Successfully fetched page content for URL: {url}")
            else:
                sdfFetch.print_error_message("error", f"Failed to fetch page content for URL: {url}")

            crawl_status.update_progress(
                self.project_name, self.site_name, schedule_key,
                retriever_fetched=fetched_count
            )
            metadata_file = output_dir / f"{schedule_key}_queue.txt"
            with open(metadata_file, "a") as file:
                file.write(str(data) + "\n")

        sdfFetch.print_info_message(
            "success",
            f"[retriever] Completed schedule_id={schedule_key} | Pages fetched: {fetched_count}/{len(output_queue)}"
        )

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python url_retriever.py <project_name> <site_name> <schedule_key>")
        sys.exit(1)
    project_name = sys.argv[1]
    site_name = sys.argv[2]
    schedule_key = sys.argv[3]
    url_retriever = UrlRetriever(base_dir,project_name,site_name)
    url_retriever.main(schedule_key)