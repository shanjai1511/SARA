from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin
import re as _re
import json as _json

BASE = "https://www.myntra.com"


def _extract_products_from_page(raw_html: str) -> list[dict]:
    """Return the embedded products list from Myntra's JS state."""
    # Products are embedded in a script as: "products":[{...}]
    idx = raw_html.find('"products":[{')
    if idx < 0:
        return []
    pos = raw_html.index('[', idx)
    depth = 0
    for i, c in enumerate(raw_html[pos:]):
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                try:
                    return _json.loads(raw_html[pos:pos + i + 1])
                except Exception:
                    return []
    return []


class MyntraComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        """Myntra uses ?p=N for pagination. Generate pages 2-11."""
        pagination_url = []
        try:
            connector = "&" if "?" in keyurl else "?"
            for p in range(2, 12):
                pagination_url.append(f"{keyurl}{connector}p={p}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        """
        Products are rendered client-side via JS but their data is embedded in
        the page's JS state.  Extract landingPageUrl from each product object.
        """
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            raw_html = dom.get("page_doc", "")
            products = _extract_products_from_page(raw_html)
            if not products:
                raise Exception("No products found in page JS state")
            seen = set()
            for rank, p in enumerate(products, 1):
                landing = p.get("landingPageUrl", "")
                if not landing:
                    continue
                # landingPageUrl uses \u002F escapes; decode already done by json.loads
                # Ensure it starts with /
                if not landing.startswith("/"):
                    landing = "/" + landing
                full = BASE + landing
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
