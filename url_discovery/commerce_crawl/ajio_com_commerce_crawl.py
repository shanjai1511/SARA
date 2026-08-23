from sdf_module.url_discovery import *
import logging
import json
import os

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Ajio.com URL Discovery
#
# Ajio is protected by Akamai Bot Manager, which blocks requests based on:
#   - TLS fingerprint (JA3 hash — Python requests ≠ Chrome)
#   - Missing sec-ch-ua / sec-fetch-* browser headers
#   - IP reputation (datacenter IPs are flagged)
#
# Fetch strategy (in order):
#   1. curl_cffi with Chrome TLS impersonation — fastest, no proxy needed
#   2. SARA Unblock Service — escalates to cffi+proxy or browser if needed
#   3. Direct requests — last resort (will likely 403 on some routes)
#
# Their internal JSON search API is used for discovery (more reliable than
# scraping category HTML pages):
#   GET /api/category/search?fields=SITE&currentPage=N&pageSize=45
#                            &format=json&query=%3Arelevance&fnl=<cat_code>
#
# Category codes come from the seed URL path:
#   ajio.com/men-tshirts-polos/c/830301001  →  fnl=830301001
# ──────────────────────────────────────────────────────────────────────────────

try:
    from curl_cffi import requests as _cf_requests
    _CURL_CFFI_AVAILABLE = True
    logger.info("Ajio discovery: curl_cffi available (Chrome TLS impersonation active)")
except ImportError:
    _CURL_CFFI_AVAILABLE = False
    import requests as _cf_requests
    logger.warning("Ajio discovery: curl_cffi not installed — falling back to requests (expect 403s)")

_API_BASE  = "https://www.ajio.com/api/category/search"
_PAGE_SIZE = 45
_MAX_PAGES = 10

_UNBLOCK_URL = os.environ.get("SARA_UNBLOCK_URL", "").rstrip("/")
_UNBLOCK_KEY = os.environ.get("SARA_UNBLOCK_API_KEY", "")

_BROWSER_HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.ajio.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua":          '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest":     "empty",
    "sec-fetch-mode":     "cors",
    "sec-fetch-site":     "same-origin",
}


# ── Fetch helpers ──────────────────────────────────────────────────────────────

def _cffi_get(url: str, session=None, timeout: int = 30) -> dict:
    """Fetch via curl_cffi (Chrome TLS impersonation)."""
    try:
        if session is None:
            resp = _cf_requests.get(
                url,
                headers=_BROWSER_HEADERS,
                impersonate="chrome124" if _CURL_CFFI_AVAILABLE else None,
                timeout=timeout,
                verify=False,
            )
        else:
            resp = session.get(url, timeout=timeout)
        return {"page_doc": resp.text, "status_code": resp.status_code, "url": url}
    except Exception as exc:
        logger.debug("cffi fetch failed for %s: %s", url, exc)
        return {"page_doc": "", "status_code": None, "url": url}


def _unblock_get(url: str, timeout: int = 60) -> dict:
    """
    Call the SARA Unblock Service to fetch a URL.
    Used as fallback when curl_cffi gets blocked.
    """
    if not _UNBLOCK_URL:
        return {"page_doc": "", "status_code": None, "url": url}
    try:
        import requests as _req
        headers = {"Content-Type": "application/json"}
        if _UNBLOCK_KEY:
            headers["Authorization"] = f"Bearer {_UNBLOCK_KEY}"
        resp = _req.post(
            f"{_UNBLOCK_URL}/fetch",
            json={
                "url":          url,
                "strategy":     2,    # start at cffi — avoids unnecessary plain-HTTP attempt
                "max_strategy": 5,
                "referer":      "https://www.ajio.com/",
            },
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and data.get("page_doc"):
                logger.info(
                    "Unblock service: strategy=%s status=%s url=%s",
                    data.get("strategy"), data.get("status_code"), url,
                )
                return {
                    "page_doc":    data["page_doc"],
                    "status_code": data.get("status_code", 200),
                    "url":         data.get("final_url", url),
                }
    except Exception as exc:
        logger.debug("Unblock service unavailable: %s", exc)
    return {"page_doc": "", "status_code": None, "url": url}


def _ajio_fetch(url: str, session=None, timeout: int = 30) -> dict:
    """
    Fetch a URL with Ajio-specific strategy:
      1. curl_cffi (fastest, no proxy)
      2. Unblock service (cffi+proxy → browser)
      3. Standard requests (last resort)
    """
    # Strategy 1: curl_cffi
    result = _cffi_get(url, session=session, timeout=timeout)
    if result["status_code"] == 200:
        return result

    status = result["status_code"]
    logger.debug("curl_cffi got status=%s for %s — escalating", status, url)

    # Strategy 2: Unblock service
    if _UNBLOCK_URL:
        result = _unblock_get(url, timeout=timeout + 30)
        if result["status_code"] == 200:
            return result

    # Strategy 3: plain requests (very unlikely to work on Ajio but worth trying)
    try:
        import requests as _req
        resp = _req.get(url, headers=_BROWSER_HEADERS, timeout=timeout, verify=True)
        return {"page_doc": resp.text, "status_code": resp.status_code, "url": url}
    except Exception as exc:
        logger.warning("All fetch strategies failed for %s: %s", url, exc)

    return result  # return last result (may be empty)


# ── Discovery class ────────────────────────────────────────────────────────────

class AjioComCommerceCrawl():

    def __init__(self):
        # Per-instance session so concurrent discovery runs don't share cookies
        if _CURL_CFFI_AVAILABLE:
            self._session = _cf_requests.Session(impersonate="chrome124")
            self._session.headers.update(_BROWSER_HEADERS)
        else:
            import requests as _req
            self._session = _req.Session()
            self._session.headers.update(_BROWSER_HEADERS)

    def _warm_session(self, category_url: str) -> None:
        """
        Fetch the HTML category page to let Akamai set session cookies.
        These cookies are required for the JSON API calls to succeed.
        Even a 403 response can still set valid session cookies.
        """
        result = _ajio_fetch(category_url, session=self._session, timeout=20)
        logger.debug(
            "Session warm: status=%s url=%s",
            result["status_code"], category_url,
        )

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        """
        Warm the session with the browse category page (sets Akamai cookies),
        then return API endpoint URLs for pages 0 … _MAX_PAGES-1.

        keyurl: https://www.ajio.com/men-tshirts-polos/c/830301001
        Returns: [API URL for page 0, page 1, …, page N]
        """
        pagination_url = []
        try:
            # Extract category code from URL path  (…/c/830301001 → 830301001)
            parts = keyurl.rstrip("/").split("/")
            try:
                c_idx    = parts.index("c")
                cat_code = parts[c_idx + 1]
            except (ValueError, IndexError):
                cat_code = parts[-1]   # fallback: last segment

            if not cat_code.isdigit():
                logger.warning("Could not extract category code from: %s", keyurl)
                return []

            # Warm session with the category HTML page
            self._warm_session(keyurl)

            for page in range(0, _MAX_PAGES):
                api_url = (
                    f"{_API_BASE}?fields=SITE"
                    f"&currentPage={page}"
                    f"&pageSize={_PAGE_SIZE}"
                    f"&format=json"
                    f"&query=%3Arelevance"
                    f"&fnl={cat_code}"
                )
                pagination_url.append(api_url)

        except Exception as exc:
            logger.warning("Exception occurred: %s", exc)

        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        """
        Fetch one page of Ajio's category JSON API and return product page URLs.
        Returns [] on an empty page (stops pagination early).

        url:     API endpoint URL (from get_pagination_url)
        Returns: ["https://www.ajio.com/product-name/p/CODE|{'rank': N}", ...]
        """
        product_url = []
        try:
            dom = _ajio_fetch(url, session=self._session, timeout=30)

            status = dom.get("status_code")
            if status != 200:
                logger.warning(
                    "API returned status=%s for %s — stopping pagination",
                    status, url,
                )
                return []

            raw  = dom.get("page_doc", "{}")
            data = json.loads(raw) if raw.strip() else {}

            products = data.get("products", [])
            if not products:
                logger.debug("Empty page — stopping pagination for %s", url)
                return []   # signal to stop paginating

            pagination     = data.get("pagination", {})
            current_page   = pagination.get("currentPage", 0)
            total_pages    = pagination.get("totalNumberOfPages", _MAX_PAGES)
            rank_start     = current_page * _PAGE_SIZE + 1

            logger.info(
                "Ajio API page %d/%d: %d products",
                current_page + 1, total_pages, len(products),
            )

            seen = set()
            rank = rank_start
            for prod in products:
                prod_path = prod.get("url", "")
                if not prod_path:
                    continue
                full = (
                    "https://www.ajio.com" + prod_path
                    if prod_path.startswith("/")
                    else prod_path
                )
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
                rank += 1

        except json.JSONDecodeError as exc:
            logger.warning("JSON decode error for %s: %s", url, exc)
        except Exception as exc:
            logger.warning("Exception occurred: %s", exc)

        return product_url
