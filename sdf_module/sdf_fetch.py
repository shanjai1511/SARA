from .files_import import *
from contextvars import ContextVar
import logging.handlers
import threading as _threading

# Crawl context for structured logging (stage, schedule_id, project, site)
_crawl_context: ContextVar[dict] = ContextVar("crawl_context", default={})

# ── Thread-local HTTP session pool ────────────────────────────────────────────
# Each worker thread keeps one long-lived Session, enabling TCP keepalive and
# connection reuse across requests on the same thread.
_thread_local = _threading.local()

# ── Domain-level circuit breaker ──────────────────────────────────────────────
# Trips after _CB_FAIL_THRESHOLD consecutive non-retryable failures (403, 404)
# on the same domain. While open, requests are skipped immediately to avoid
# hammering blocked sites.  Resets automatically after _CB_OPEN_SECONDS.
_CB_FAIL_THRESHOLD = 5       # consecutive failures to trip
_CB_OPEN_SECONDS   = 300     # seconds circuit stays open (5 min)

_domain_circuit: dict = {}   # domain → {"fails": int, "open_until": float|None}
_circuit_lock = _threading.Lock()


def _cb_is_open(domain: str) -> bool:
    """Return True if the circuit for *domain* is open (requests should be skipped)."""
    with _circuit_lock:
        state = _domain_circuit.get(domain)
        if not state:
            return False
        open_until = state.get("open_until")
        if open_until and time.time() < open_until:
            return True
        if open_until:
            # Timer expired — half-open: allow one probe through
            state["open_until"] = None
        return False


def _cb_record_failure(domain: str, status_code: int) -> None:
    """Record a non-retryable failure for *domain* and trip circuit if threshold hit."""
    if status_code not in (403, 404, 407):
        return
    with _circuit_lock:
        state = _domain_circuit.setdefault(domain, {"fails": 0, "open_until": None})
        state["fails"] += 1
        if state["fails"] >= _CB_FAIL_THRESHOLD:
            state["open_until"] = time.time() + _CB_OPEN_SECONDS
            logging.warning(
                "Circuit OPEN for domain=%s after %d consecutive %d responses "
                "(will retry after %ds)",
                domain, state["fails"], status_code, _CB_OPEN_SECONDS,
            )


def _cb_record_success(domain: str) -> None:
    """Reset circuit state for *domain* on a successful fetch."""
    with _circuit_lock:
        _domain_circuit.pop(domain, None)


def _get_thread_session() -> requests.Session:
    """Return (or create) a per-thread requests.Session with default headers."""
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        _thread_local.session = s
    return _thread_local.session


# constants and shared objects
DEFAULT_RETRY_STATUSES = (429, 500, 502, 503, 504)
LOG_FILE = Path(base_dir) / "logs" / "pipeline.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
CACHE_DIR = Path(base_dir) / "cache"
CACHE_MAX_AGE_HOURS = 24


def _cleanup_old_cache() -> None:
    """Delete cache files older than CACHE_MAX_AGE_HOURS to prevent disk fill."""
    if not CACHE_DIR.exists():
        return
    cutoff = time.time() - CACHE_MAX_AGE_HOURS * 3600
    for f in CACHE_DIR.glob("*.html"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except Exception:
            pass

# Configure logging only once so imports don't reconfigure.
# Use RotatingFileHandler to prevent unbounded log growth (10 MB × 5 files).
if not logging.getLogger().handlers:
    _fh = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _sh = logging.StreamHandler(sys.stdout)
    _sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[_fh, _sh])

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unblock service client (optional — only active when SARA_UNBLOCK_URL is set)
# ---------------------------------------------------------------------------
import os as _os

_UNBLOCK_URL  = _os.environ.get("SARA_UNBLOCK_URL", "").rstrip("/")
_UNBLOCK_KEY  = _os.environ.get("SARA_UNBLOCK_API_KEY", "")
_UNBLOCK_TIMEOUT = 120   # seconds — browser strategies can take a while


def _unblock_fetch(url: str, domain: str) -> dict | None:
    """
    Call the sara-unblock service to bypass anti-bot blocking.
    Returns a sdfFetch-compatible dict or None if the service is unavailable.
    """
    if not _UNBLOCK_URL:
        return None
    try:
        import requests as _req
        headers = {"Content-Type": "application/json"}
        if _UNBLOCK_KEY:
            headers["Authorization"] = f"Bearer {_UNBLOCK_KEY}"
        resp = _req.post(
            f"{_UNBLOCK_URL}/fetch",
            json={"url": url, "strategy": 0, "max_strategy": 5},
            headers=headers,
            timeout=_UNBLOCK_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and data.get("page_doc"):
                logger.info(
                    "UnblockService: SUCCESS strategy=%s status=%s url=%s",
                    data.get("strategy"), data.get("status_code"), url,
                )
                return {
                    "page_doc":    data["page_doc"],
                    "status_code": data.get("status_code", 200),
                    "url":         data.get("final_url", url),
                }
        logger.debug("UnblockService returned non-OK for %s: %s", url, resp.text[:200])
        return None
    except Exception as exc:
        logger.debug("UnblockService unavailable: %s", exc)
        return None

# Import metrics lazily so the module is usable without prometheus_client installed.
try:
    from core.metrics import metrics as _metrics
except Exception:
    class _NoOpMetrics:
        def fetch_success(self, *a, **k): pass
        def fetch_failure(self, *a, **k): pass
        def fetch_timer(self, domain=""):
            from contextlib import contextmanager
            @contextmanager
            def _noop(): yield
            return _noop()
    _metrics = _NoOpMetrics()


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
    def print_error_message(status, info, url=None):
        status_message = {"status": status, "info": info}
        if url is not None:
            status_message["url"] = url
        status_message = sdfFetch._merge_context(status_message)
        logging.error(json.dumps(status_message, indent=4))

    @staticmethod
    def get_rabbitmq_channel(max_attempts: int = 3, base_backoff: float = 2.0):
        """Connect to RabbitMQ with exponential back-off retry.

        Raises the last exception if all attempts are exhausted.
        """
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
    def print_info_message(status, info=None, url=None):
        status_message = {"status": status, "info": info}
        if url is not None:
            status_message["url"] = url
        status_message = sdfFetch._merge_context(status_message)
        logging.info(json.dumps(status_message, indent=4))

    @staticmethod
    def get_page_content_hash(
        url: str,
        proxy: str | None = None,
        extended_header: dict | None = None,
        max_retries: int = 3,
        timeout: int = 30,
        retry_statuses: tuple[int, ...] | None = None,
    ) -> dict:
        """
        Fetch page content with retries and optional proxy.

        Uses a per-thread :class:`requests.Session` for connection reuse.
        Returns a dictionary with ``page_doc`` (text), ``status_code`` and ``url``.
        """
        if not url:
            sdfFetch.print_error_message("error", "Invalid URL")
            return {"page_doc": "", "status_code": None, "url": url}

        # Fix 2: clean up stale cache files periodically (1-in-50 chance per call)
        if random.randint(1, 50) == 1:
            _cleanup_old_cache()

        retry_statuses = retry_statuses or DEFAULT_RETRY_STATUSES

        session = _get_thread_session()
        if extended_header:
            session.headers.update(extended_header)

        # Build per-request proxy dict using ProxyManager (health-aware selection).
        # NOT session-level so proxy config doesn't bleed across requests on the same thread.
        request_proxies  = None
        _active_proxy_url: str | None = None   # tracks which proxy is currently active

        if proxy == "webshare_proxy":
            from core.proxy_manager import get_proxy_manager
            _proxy_mgr    = get_proxy_manager()
            _active_proxy_url = _proxy_mgr.get_proxy_for_request(_domain)
            if _active_proxy_url:
                request_proxies = {"http": _active_proxy_url, "https": _active_proxy_url}
            elif webshare_proxy:
                # Fallback: all ProxyManager slots in cooldown — random raw entry
                host, port, username, password = random.choice(webshare_proxy)
                _active_proxy_url = f"http://{username}:{password}@{host}:{port}"
                request_proxies   = {"http": _active_proxy_url, "https": _active_proxy_url}
            else:
                logging.warning("proxy='webshare_proxy' requested but no proxies configured — fetching directly")
        else:
            _proxy_mgr = None

        # Circuit breaker: skip entirely if domain is blocked
        from urllib.parse import urlparse as _urlparse
        _domain = _urlparse(url).netloc or url
        if _cb_is_open(_domain):
            # Circuit is open — try unblock service before skipping entirely
            logging.warning("Circuit OPEN for domain=%s — trying unblock service", _domain)
            unblock_result = _unblock_fetch(url, _domain)
            if unblock_result:
                _cb_record_success(_domain)
                _metrics.fetch_success(_domain)
                return unblock_result
            logging.warning("Unblock service also failed — skipping %s", url)
            return {"page_doc": "", "status_code": None, "url": url}

        last_response = None

        for attempt in range(max_retries + 1):
            active_proxies = (
                {"http": _active_proxy_url, "https": _active_proxy_url}
                if _active_proxy_url else None
            )

            try:
                msg = f"Fetching page content for URL: {url}"
                if attempt > 0:
                    proxy_tag = f" via {_active_proxy_url[-20:] if _active_proxy_url else 'direct'}"
                    msg += f" (attempt {attempt + 1}/{max_retries + 1}{proxy_tag})"
                sdfFetch.print_info_message("info", msg)

                _t0 = time.time()
                with _metrics.fetch_timer(_domain):
                    response = session.get(url, verify=True, timeout=timeout, proxies=active_proxies)
                _latency_ms = (time.time() - _t0) * 1000
                last_response = response

                status = response.status_code
                if status == 200:
                    _cb_record_success(_domain)
                    _metrics.fetch_success(_domain)
                    if _active_proxy_url and proxy == "webshare_proxy":
                        _proxy_mgr.report_success(_domain, _active_proxy_url, latency_ms=_latency_ms)
                    output_dir = Path(base_dir) / "cache"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_file = output_dir / f"{sdfFetch.encode(url)}.html"
                    with open(output_file, "wb") as f:
                        f.write(response.content)
                    sdfFetch.print_info_message("success", "Page fetched successfully.", url=str(output_file))
                    return {"page_doc": response.text, "status_code": status, "url": url}

                if status in (403, 429):
                    # Record block and rotate to a different proxy before next attempt
                    if _active_proxy_url and proxy == "webshare_proxy":
                        blocked = (status == 403)
                        _proxy_mgr.report_failure(_domain, _active_proxy_url, blocked=blocked)
                        next_proxy = _proxy_mgr.get_proxy(_domain, exclude=_active_proxy_url)
                        if next_proxy and next_proxy != _active_proxy_url:
                            logging.info(
                                "Proxy blocked (status %d) — rotating to new proxy for %s",
                                status, _domain,
                            )
                            _active_proxy_url = next_proxy
                            if attempt < max_retries:
                                sleep(1)
                                continue

                    # All proxies exhausted or no proxy — try unblock service
                    unblock_result = _unblock_fetch(url, _domain)
                    if unblock_result:
                        _cb_record_success(_domain)
                        _metrics.fetch_success(_domain)
                        return unblock_result

                    _cb_record_failure(_domain, status)
                    _metrics.fetch_failure(_domain, f"http_{status}")
                    sdfFetch.print_error_message(
                        "error",
                        f"Failed to fetch page content for URL: {url} (status {status})",
                    )
                    return {"page_doc": "", "status_code": status, "url": url}

                if status in retry_statuses and attempt < max_retries:
                    if _active_proxy_url and proxy == "webshare_proxy":
                        _proxy_mgr.report_failure(_domain, _active_proxy_url, blocked=False)
                    backoff = 2 ** attempt
                    sdfFetch.print_info_message("info", f"Retrying in {backoff}s (status {status})")
                    sleep(backoff)
                    continue

                # Other non-retryable failure
                _metrics.fetch_failure(_domain, f"http_{status}")
                sdfFetch.print_error_message(
                    "error",
                    f"Failed to fetch page content for URL: {url} (status {status})",
                )
                return {"page_doc": "", "status_code": status, "url": url}

            except requests.exceptions.ProxyError as e:
                if _active_proxy_url and proxy == "webshare_proxy":
                    _proxy_mgr.report_failure(_domain, _active_proxy_url, blocked=False)
                    # Rotate to a different proxy
                    next_proxy = _proxy_mgr.get_proxy(_domain, exclude=_active_proxy_url)
                    if next_proxy:
                        logging.warning("ProxyError — rotating proxy for %s: %s", _domain, e)
                        _active_proxy_url = next_proxy
                        continue
                # No more proxies — fall back to direct
                logging.warning("All proxies failed — going direct for %s", url)
                _active_proxy_url = None
                if attempt < max_retries:
                    continue
                _metrics.fetch_failure(_domain, "proxy_error")
                sdfFetch.print_error_message("error", f"Proxy and direct fallback failed for URL: {url}: {e}", url=url)
                break

            except requests.RequestException as e:
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    sdfFetch.print_info_message("info", f"Request failed ({e}), retrying in {backoff}s")
                    sleep(backoff)
                    continue
                _metrics.fetch_failure(_domain, "request_exception")
                sdfFetch.print_error_message(
                    "error",
                    f"Request failed for URL: {url} after {max_retries + 1} attempts: {e}",
                    url=url,
                )
                logger.exception("Request failed")
                break

        return {
            "page_doc": "",
            "status_code": getattr(last_response, "status_code", None)
            if last_response
            else None,
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
            logging.exception("CSS selector extraction failed")
            return None

    @staticmethod
    def encode(array):
        sdfFetch.print_info_message("info", "Encoding input")
        combined_str = array if isinstance(array, str) else ''.join(str(x) for x in array)
        unique_id = hashlib.md5(combined_str.encode()).hexdigest()
        sdfFetch.print_info_message("success", "Array encoded successfully")
        return unique_id
