from .files_import import *
import logging.handlers
import os as _os

DEFAULT_RETRY_STATUSES = (429, 500, 502, 503, 504)

# ── Bot-page detection ────────────────────────────────────────────────────────
# Amazon (and others) return 200 but serve a CAPTCHA/robot-check page.
# Detect these by looking for known bot-challenge strings in the body.
_BOT_SIGNALS = (
    "captcha",
    "robot check",
    "Type the characters you see",
    "Sorry, we just need to make sure",
    "api-services.amazon",  # Amazon bot-check JS endpoint
)

def _is_bot_page(text: str) -> bool:
    """Return True if the 200-OK response is actually a bot-challenge page."""
    sample = text[:8000].lower()
    return any(sig.lower() in sample for sig in _BOT_SIGNALS)


# ── Unblock service client ────────────────────────────────────────────────────
_UNBLOCK_URL     = _os.environ.get("SARA_UNBLOCK_URL", "").rstrip("/")
_UNBLOCK_KEY     = _os.environ.get("SARA_UNBLOCK_API_KEY", "")
_UNBLOCK_TIMEOUT = 120   # Playwright strategies can take a while


def _unblock_fetch(url: str) -> dict | None:
    """
    Call the local sara-unblock service (Playwright-backed) to bypass bot checks.
    Returns a sdfFetch-compatible dict or None if the service is unavailable.
    """
    # Re-read env at call time so subprocesses pick up .env changes without restart.
    unblock_url = _os.environ.get("SARA_UNBLOCK_URL", "").rstrip("/") or _UNBLOCK_URL
    if not unblock_url:
        return None
    try:
        headers = {"Content-Type": "application/json"}
        if _UNBLOCK_KEY:
            headers["Authorization"] = f"Bearer {_UNBLOCK_KEY}"
        resp = requests.post(
            f"{unblock_url}/fetch",
            json={"url": url, "strategy": 4, "max_strategy": 5},
            headers=headers,
            timeout=_UNBLOCK_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and data.get("page_doc"):
                logger_ref = logging.getLogger(__name__)
                logger_ref.info("UnblockService: SUCCESS strategy=%s url=%s", data.get("strategy"), url)
                return {
                    "page_doc":    data["page_doc"],
                    "status_code": data.get("status_code", 200),
                    "url":         data.get("final_url", url),
                }
    except Exception as exc:
        logging.getLogger(__name__).debug("UnblockService unavailable for %s: %s", url, exc)
    return None
LOG_FILE = Path(base_dir) / "logs" / "pipeline.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

if not logging.getLogger().handlers:
    _fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[_fh, _sh])

logger = logging.getLogger(__name__)


class sdfFetch:
    @staticmethod
    def print_error_message(status, info, url=None):
        msg = {"status": status, "info": info}
        if url is not None:
            msg["url"] = url
        logging.error(json.dumps(msg, indent=4))

    @staticmethod
    def print_info_message(status, info=None, url=None):
        msg = {"status": status, "info": info}
        if url is not None:
            msg["url"] = url
        logging.info(json.dumps(msg, indent=4))

    @staticmethod
    def get_rabbitmq_channel(max_attempts: int = 3, base_backoff: float = 2.0):
        params = pika.URLParameters(CLOUDAMQP_URL)
        last_exc = None
        for attempt in range(max_attempts):
            try:
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                return connection, channel
            except Exception as exc:
                last_exc = exc
                wait = base_backoff ** attempt
                logger.warning(
                    "RabbitMQ connection attempt %d/%d failed (%s). Retrying in %.0fs.",
                    attempt + 1, max_attempts, exc, wait,
                )
                sleep(wait)
        raise last_exc

    @staticmethod
    def get_page_content_hash(
        url: str,
        proxy: str | None = None,
        extended_header: dict | None = None,
        max_retries: int = 3,
        timeout: int = 30,
        retry_statuses: tuple[int, ...] | None = None,
    ) -> dict:
        if not url:
            sdfFetch.print_error_message("error", "Invalid URL")
            return {"page_doc": "", "status_code": None, "url": url}

        retry_statuses = retry_statuses or DEFAULT_RETRY_STATUSES

        headers = dict(_HEADERS)
        if extended_header:
            headers.update(extended_header)

        request_proxies = None
        if proxy == "webshare_proxy" and webshare_proxy:
            host, port, username, password = random.choice(webshare_proxy)
            proxy_url = f"http://{username}:{password}@{host}:{port}"
            request_proxies = {"http": proxy_url, "https": proxy_url}

        last_response = None
        for attempt in range(max_retries + 1):
            try:
                msg = f"Fetching page content for URL: {url}"
                if attempt > 0:
                    msg += f" (attempt {attempt + 1}/{max_retries + 1})"
                sdfFetch.print_info_message("info", msg)

                response = requests.get(
                    url, headers=headers, verify=True, timeout=timeout, proxies=request_proxies
                )
                last_response = response
                status = response.status_code

                if status == 200:
                    text = response.text
                    if _is_bot_page(text):
                        logging.getLogger(__name__).warning(
                            "Bot-challenge page detected (200 but CAPTCHA) for %s — trying unblock service", url
                        )
                        unblock = _unblock_fetch(url)
                        if unblock:
                            text = unblock["page_doc"]
                        else:
                            # Unblock unavailable — return empty so parser skips this URL
                            return {"page_doc": "", "status_code": 403, "url": url}
                    output_dir = Path(base_dir) / "cache"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{sdfFetch.encode(url)}.html"
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(text)
                    sdfFetch.print_info_message("success", "Page fetched successfully.", url=str(output_file))
                    return {"page_doc": text, "status_code": 200, "url": url}

                if status in retry_statuses and attempt < max_retries:
                    backoff = 2 ** attempt
                    sdfFetch.print_info_message("info", f"Retrying in {backoff}s (status {status})")
                    sleep(backoff)
                    continue

                # Retries exhausted — try unblock service before giving up
                unblock = _unblock_fetch(url)
                if unblock:
                    return unblock

                sdfFetch.print_error_message(
                    "error", f"Failed to fetch page content for URL: {url} (status {status})"
                )
                return {"page_doc": "", "status_code": status, "url": url}

            except requests.RequestException as e:
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    sdfFetch.print_info_message("info", f"Request failed ({e}), retrying in {backoff}s")
                    sleep(backoff)
                    continue
                sdfFetch.print_error_message(
                    "error",
                    f"Request failed for URL: {url} after {max_retries + 1} attempts: {e}",
                    url=url,
                )
                break

        return {
            "page_doc": "",
            "status_code": getattr(last_response, "status_code", None) if last_response else None,
            "url": url,
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
            return None

    @staticmethod
    def get_value_from_xpath(parsed_tree, xpath_expr, count, attr="none"):
        try:
            sdfFetch.print_info_message("info", f"Extracting value from XPath expression: {xpath_expr}")
            if hasattr(parsed_tree, "xpath"):
                elements = parsed_tree.xpath(xpath_expr)
                if attr != "none":
                    text_content = [el.get(attr) if el.get(attr) is not None else "" for el in elements if hasattr(el, "get")]
                else:
                    text_content = [
                        el.text_content().strip() if hasattr(el, "text_content") else str(el)
                        for el in elements if el is not None
                    ]
            else:
                elements = parsed_tree.select(xpath_expr)
                text_content = [element.get_text(strip=True) for element in elements if element]
                if attr != "none":
                    text_content = [el.get(attr, "") for el in elements if el.has_attr(attr)]
            sdfFetch.print_info_message("success", f"Value extracted from XPath expression: {xpath_expr}")
            return text_content if count == "all" else (text_content[0] if text_content else None)
        except Exception as e:
            sdfFetch.print_error_message("error", f"XPath extraction failed with error: {e}")
            return None

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
            return None

    @staticmethod
    def encode(array):
        combined_str = array if isinstance(array, str) else ''.join(str(x) for x in array)
        return hashlib.md5(combined_str.encode()).hexdigest()
