from .files_import import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f"{base_dir}/logs/pipeline.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

class sdfFetch:
    @staticmethod
    def print_error_message(status, info):
        status_message = {
            "status": status,
            "info": info
        }
        json_message = json.dumps(status_message, indent=4)
        logging.error(json_message)

    @staticmethod
    def get_rabbitmq_channel():
        params = pika.URLParameters(sdfFetch.CLOUDAMQP_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        return connection, channel


    @staticmethod
    def print_info_message(status, info=None, url=None):
        status_message = {
            "status": status,
            "info": info
        }
        if url is not None:
            status_message["url"] = url
            
        json_message = json.dumps(status_message, indent=4)
        logging.info(json_message)

    @staticmethod
    def get_page_content_hash(url, proxy=None, extended_header=None):
        if not url:
            sdfFetch.print_error_message("error", "Invalid URL")
            return {"page_doc": "", "status_code": None, "url": url}

        session = requests.Session()

        try:
            sdfFetch.print_info_message("info", f"Fetching page content for URL: {url}")

            # Attach headers if provided
            if extended_header:
                session.headers.update(extended_header)

            # Configure proxy if required
            if proxy == "webshare_proxy":
                host, port, username, password = random.choice(webshare_proxy)
                proxy_url = f"http://{username}:{password}@{host}:{port}"
                session.proxies.update({
                    "http": proxy_url,
                    "https": proxy_url
                })

            response = session.get(url, verify=False)

            result = {
                "page_doc": response.text,
                "status_code": response.status_code,
                "url": url
            }

            if response.status_code == 200:
                output_dir = Path(f"{base_dir}/cache/")
                output_dir.mkdir(parents=True, exist_ok=True)

                output_file = output_dir / f"{sdfFetch.encode(url)}.html"
                with open(output_file, "wb") as file:
                    file.write(response.content)

                sdfFetch.print_info_message(
                    "success",
                    str(output_file),
                    "Page fetched successfully."
                )
            else:
                sdfFetch.print_error_message(
                    "error",
                    f"Failed to fetch page content for URL: {url}"
                )
            return result
        except requests.RequestException as e:
            sdfFetch.print_error_message(
                "error",
                f"Request failed for URL: {url} with error: {e}"
            )
            logging.exception("Request failed")
            return {
                "page_doc": "",
                "status_code": None,
                "url": url
            }
        finally:
            session.close()

    @staticmethod
    def get_parsed_tree(page_doc, format="lxml"):
        try:
            sdfFetch.print_info_message("info", f"Parsing page document using {format}")
            if format == "lxml":
                parsed_tree = html.fromstring(page_doc["page_doc"])
                sdfFetch.print_info_message("success", "Page document parsed successfully using lxml.")
                return parsed_tree
            else:
                if type(page_doc) == dict:
                    page_doc = page_doc["page_doc"]
                soup = BeautifulSoup(page_doc, 'html5lib')
                sdfFetch.print_info_message("success", "Page document parsed successfully using beautiful soup.")
                return soup
        except Exception as e:
            sdfFetch.print_error_message("error", f"Unexpected error during parsing: {e}")
            logging.exception("Parsing failed")
            return None

    @staticmethod
    def get_value_from_xpath(parsed_tree, xpath_expr, count, attr="none"):
        try:
            sdfFetch.print_info_message("info", f"Extracting value from XPath expression: {xpath_expr}")
            elements = parsed_tree.select(xpath_expr)
            text_content = [element.get_text() for element in elements if element]
            if attr != "none":
                text_content = [link[attr] for link in elements if link.has_attr(attr)]
            sdfFetch.print_info_message("success", f"Value extracted from XPath expression: {xpath_expr}")
            return text_content if count == "all" else (text_content[0] if text_content else None)
        except Exception as e:
            sdfFetch.print_error_message("error", f"XPath extraction failed with error: {e}")
            logging.exception("XPath extraction failed")
            return f"Unexpected error: {e}"

    @staticmethod
    def get_value_from_css_selector(parsed_tree, css_selector, count, attr="none"):
        try:
            sdfFetch.print_info_message("info", f"Extracting value from CSS selector: {css_selector}")
            elements = parsed_tree.select(css_selector)
            text_content = [element.get_text() for element in elements if element]
            if attr != "none":
                text_content = [element.get(attr) for element in elements if element.has_attr(attr)]
            sdfFetch.print_info_message("success", f"Value extracted from CSS selector: {css_selector}")
            return text_content if count == "all" else (text_content[0] if text_content else None)
        except Exception as e:
            sdfFetch.print_error_message("error", f"CSS selector extraction failed with error: {e}")
            logging.exception("CSS selector extraction failed")
            return f"Unexpected error: {e}"

    @staticmethod
    def encode(array):
        sdfFetch.print_info_message("info", "Encoding array")
        combined_str = ''.join(array)
        unique_id = hashlib.md5(combined_str.encode()).hexdigest()
        sdfFetch.print_info_message("success", "Array encoded successfully")
        return unique_id