from sdf_module.url_parser import *
import logging
import json as _json
import re as _re
logger = logging.getLogger(__name__)


def _jsonld(page_doc) -> dict:
    for s in page_doc.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            d = _json.loads(s)
            if d.get("@type") == "Product":
                return d
        except Exception:
            pass
    return {}


def _script_val(page_doc, key: str):
    """Extract a numeric value by key from inline scripts."""
    for s in page_doc.xpath('//script[not(@src)]/text()'):
        m = _re.search(rf'["\']({key})["\']\\s*:\\s*(\\d+)', s, _re.I)
        if m:
            return int(m.group(2))
    return None


class NykaaFashionComCommerceCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        return []

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        return datetime.now().strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)

    @staticmethod
    def get_product_name(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("name"):
            return ld["name"].strip()
        elems = page_doc.xpath("//h1/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_brand(page_doc, inhash):
        ld = _jsonld(page_doc)
        brand = ld.get("brand", {})
        return brand.get("name", "").strip() if isinstance(brand, dict) else ""

    @staticmethod
    def get_sku(page_doc, inhash):
        ld = _jsonld(page_doc)
        return ld.get("sku", "") or ""

    @staticmethod
    def get_selling_price(page_doc, inhash):
        ld = _jsonld(page_doc)
        price = ld.get("offers", {}).get("price")
        if price is not None:
            return int(price)
        return None

    @staticmethod
    def get_list_price(page_doc, inhash):
        # MRP embedded in inline scripts
        val = _script_val(page_doc, "mrp")
        if val:
            return val
        # fallback to selling price
        return NykaaFashionComCommerceCrawl.get_selling_price(page_doc, inhash)

    @staticmethod
    def get_image_url(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("image"):
            return ld["image"]
        elems = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return elems[0].strip() if elems else ""
