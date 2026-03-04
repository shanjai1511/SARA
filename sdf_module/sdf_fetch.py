from .files_import import *

# Crawl context for structured logging (stage, schedule_id, project, site)
_crawl_context: ContextVar[dict] = ContextVar("crawl_context", default={})

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
    def set_crawl_context(stage=None, schedule_id=None, project=None, site=None):
        """Set crawl context for structured logging. Call at start of each pipeline stage."""
        ctx = {k: v for k, v in {
            "stage": stage,
            "schedule_id": schedule_id,
            "project": project,
            "site": site,
        }.items() if v is not None}
        _crawl_context.set(ctx)
        return ctx

    @staticmethod
    def _merge_context(status_message):
        ctx = _crawl_context.get()
        if ctx:
            status_message["crawl"] = ctx
        return status_message

    @staticmethod
    def print_error_message(status, info):
        sleep(2)
        status_message = {"status": status, "info": info}
        status_message = sdfFetch._merge_context(status_message)
        logging.error(json.dumps(status_message, indent=4))

    @staticmethod
    def get_rabbitmq_channel():
        params = pika.URLParameters(CLOUDAMQP_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        return connection, channel


    @staticmethod
    def print_info_message(status, info=None, url=None):
        sleep(2)
        status_message = {"status": status, "info": info}
        if url is not None:
            status_message["url"] = url
        status_message = sdfFetch._merge_context(status_message)
        logging.info(json.dumps(status_message, indent=4))

    @staticmethod
    def get_page_content_hash(url, proxy=None, extended_header=None, max_retries=3, timeout=30, retry_statuses=None):
        """
        Fetch page content with retries.

        Args:
            url: URL to fetch
            proxy: "webshare_proxy" to use proxy, or None
            extended_header: Optional dict of headers
            max_retries: Number of retries on failure (default 3)
            timeout: Request timeout in seconds (default 30)
            retry_statuses: HTTP status codes to retry (default 429, 500, 502, 503, 504)
        """
        if not url:
            sdfFetch.print_error_message("error", "Invalid URL")
            return {"page_doc": "", "status_code": None, "url": url}

        if retry_statuses is None:
            retry_statuses = (429, 500, 502, 503, 504)

        last_exception = None
        last_response = None

        for attempt in range(max_retries + 1):
            session = requests.Session()
            try:
                sdfFetch.print_info_message(
                    "info",
                    f"Fetching page content for URL: {url}" + (f" (attempt {attempt + 1}/{max_retries + 1})" if attempt > 0 else "")
                )

                if extended_header:
                    session.headers.update(extended_header)

                if proxy == "webshare_proxy":
                    host, port, username, password = random.choice(webshare_proxy)
                    proxy_url = f"http://{username}:{password}@{host}:{port}"
                    session.proxies.update({"http": proxy_url, "https": proxy_url})

                response = session.get(url, verify=False, timeout=timeout)
                last_response = response

                if response.status_code == 200:
                    output_dir = Path(f"{base_dir}/cache/")
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{sdfFetch.encode(url)}.html"
                    with open(output_file, "wb") as file:
                        file.write(response.content)
                    sdfFetch.print_info_message(
                        "success",
                        "Page fetched successfully.",
                        url=str(output_file)
                    )
                    return {
                        "page_doc": response.text,
                        "status_code": response.status_code,
                        "url": url
                    }

                if response.status_code in retry_statuses and attempt < max_retries:
                    backoff = 2 ** attempt
                    sdfFetch.print_info_message(
                        "info",
                        f"Retrying in {backoff}s (status {response.status_code})"
                    )
                    sleep(backoff)
                else:
                    sdfFetch.print_error_message(
                        "error",
                        f"Failed to fetch page content for URL: {url} (status {response.status_code})"
                    )
                    return {
                        "page_doc": "",
                        "status_code": response.status_code,
                        "url": url
                    }

            except requests.RequestException as e:
                last_exception = e
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    sdfFetch.print_info_message(
                        "info",
                        f"Request failed ({e}), retrying in {backoff}s"
                    )
                    sleep(backoff)
                else:
                    sdfFetch.print_error_message(
                        "error",
                        f"Request failed for URL: {url} after {max_retries + 1} attempts: {e}"
                    )
                    logging.exception("Request failed")
            finally:
                session.close()

        return {
            "page_doc": "",
            "status_code": getattr(last_response, "status_code", None) if last_response else None,
            "url": url
        }

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
            if hasattr(parsed_tree, "xpath"):
                # lxml element
                elements = parsed_tree.xpath(xpath_expr)
                if attr != "none":
                    text_content = [el.get(attr) if el.get(attr) is not None else "" for el in elements if hasattr(el, "get")]
                else:
                    text_content = [
                        el.text_content().strip() if hasattr(el, "text_content") else str(el)
                        for el in elements if el is not None
                    ]
            else:
                # BeautifulSoup - no native XPath; use cssselect via lxml if available
                elements = parsed_tree.select(xpath_expr)  # CSS selector fallback
                text_content = [element.get_text(strip=True) for element in elements if element]
                if attr != "none":
                    text_content = [el.get(attr, "") for el in elements if el.has_attr(attr)]
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
            if hasattr(parsed_tree, "cssselect"):
                elements = parsed_tree.cssselect(css_selector)
                if attr != "none":
                    text_content = [el.get(attr, "") for el in elements if hasattr(el, "get")]
                else:
                    text_content = [
                        el.text_content().strip() if hasattr(el, "text_content") else str(el)
                        for el in elements if el is not None
                    ]
            else:
                elements = parsed_tree.select(css_selector)
                text_content = [element.get_text(strip=True) for element in elements if element]
                if attr != "none":
                    text_content = [element.get(attr, "") for element in elements if element.has_attr(attr)]
            sdfFetch.print_info_message("success", f"Value extracted from CSS selector: {css_selector}")
            return text_content if count == "all" else (text_content[0] if text_content else None)
        except Exception as e:
            sdfFetch.print_error_message("error", f"CSS selector extraction failed with error: {e}")
            logging.exception("CSS selector extraction failed")
            return f"Unexpected error: {e}"

    @staticmethod
    def encode(array):
        sdfFetch.print_info_message("info", "Encoding input")
        combined_str = array if isinstance(array, str) else ''.join(str(x) for x in array)
        unique_id = hashlib.md5(combined_str.encode()).hexdigest()
        sdfFetch.print_info_message("success", "Array encoded successfully")
        return unique_id
