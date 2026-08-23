from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
import json as _json
import re as _re

BASE = "https://www.shoppersstop.com"


def _slugify(title: str) -> str:
    s = title.lower().strip()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _products_from_next_data(raw_html: str) -> list:
    """Extract products list from __NEXT_DATA__ Browse query."""
    idx = raw_html.find('"__NEXT_DATA__"')
    if idx < 0:
        # Try as script tag content
        m = _re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', raw_html, _re.S)
        if not m:
            return []
        raw = m.group(1)
    else:
        # Inline assignment
        start = raw_html.index('{', idx)
        depth = 0
        end = start
        for i, c in enumerate(raw_html[start:]):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
        raw = raw_html[start:end]

    try:
        data = _json.loads(raw)
    except Exception:
        return []

    # Path: props.pageProps.dehydratedState.queries[*].state.data.response.products
    queries = (
        data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])
    )
    for q in queries:
        products = (
            q.get("state", {})
             .get("data", {})
             .get("response", {})
             .get("products", [])
        )
        if products:
            return products

    # Fallback: search for "products" key anywhere in response
    def _find_products(obj, depth=0):
        if depth > 8:
            return []
        if isinstance(obj, dict):
            if "products" in obj and isinstance(obj["products"], list) and obj["products"]:
                return obj["products"]
            for v in obj.values():
                result = _find_products(v, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = _find_products(item, depth + 1)
                if result:
                    return result
        return []

    return _find_products(data)


class ShoppersstopComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            connector = "&" if "?" in keyurl else "?"
            for p in range(2, 12):
                pagination_url.append(f"{keyurl}{connector}page={p}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            raw_html = dom.get("page_doc", "")
            products = _products_from_next_data(raw_html)
            if not products:
                raise Exception("No products found in __NEXT_DATA__")
            seen = set()
            rank = 1
            for p in products:
                title = p.get("title", "")
                uid = p.get("uniqueId", "")
                if not title or not uid:
                    continue
                slug = _slugify(title)
                sku = p.get("sku", "")
                if sku:
                    full = f"{BASE}/{slug}/p/{sku}"
                else:
                    full = f"{BASE}/{slug}/{uid}"
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
                rank += 1
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
