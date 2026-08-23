from sdf_module.url_discovery import *
import logging
import json as _json
import re as _re
logger = logging.getLogger(__name__)

# indiaretailing.com relaunched on Next.js (www.indiaretailing.com). Category
# listing pages (e.g. /categories/fashion-lifestyle) render their article
# list server-side into a __NEXT_DATA__ JSON blob rather than plain <a href>
# links, and articles live at flat top-level slugs: BASE/{route}. There is no
# working ?page=/N pagination on these listing pages (every page number
# returns the same fixed list), so depth1 is a no-op passthrough.
BASE = "https://www.indiaretailing.com"


def _routes_from_next_data(raw_html: str) -> list:
    m = _re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', raw_html, _re.S)
    if not m:
        return []
    try:
        data = _json.loads(m.group(1))
    except Exception:
        return []
    values = data.get("props", {}).get("pageProps", {}).get("values", [])
    return [v.get("route") for v in values if v.get("route")]


class IndiaRetailingComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        # No working pagination on Next.js category pages; pass the seed through.
        return [keyurl]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No DOM")
            routes = _routes_from_next_data(dom.get("page_doc", ""))
            seen = set()
            for route in routes:
                full = f"{BASE}/{route}"
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
