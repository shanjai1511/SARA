from sdf_module.url_parser import *
import logging
import json as _json
import re as _re

logger = logging.getLogger(__name__)


def _json_ld(page_doc) -> dict:
    """Return the first Product JSON-LD block, or {}."""
    for s in page_doc.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            d = _json.loads(s)
            if isinstance(d, list):
                d = d[0]
            if isinstance(d, dict) and d.get("@type") == "Product":
                return d
        except Exception:
            pass
    return {}


def _extract_price(text: str) -> int | None:
    """Extract first integer from a string like ': ₹ 999' or 'M.R.P.: ₹ 999'."""
    m = _re.search(r'[\d,]+', text.replace(",", ""))
    if m:
        try:
            return int(_re.sub(r"\D", "", m.group(0)))
        except ValueError:
            pass
    return None


class LimeroadComCommerceCrawl():

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
        d = _json_ld(page_doc)
        if d.get("name"):
            return d["name"].title()
        for h in page_doc.xpath("//h1"):
            t = "".join(h.itertext()).strip()
            if t:
                return t
        return None

    @staticmethod
    def get_brand(page_doc, inhash):
        d = _json_ld(page_doc)
        brand = d.get("brand", {})
        if isinstance(brand, dict):
            return brand.get("name")
        return None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        d = _json_ld(page_doc)
        price = d.get("offers", {}).get("price")
        if price:
            try:
                return int(float(str(price).replace(",", "")))
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def get_list_price(page_doc, inhash):
        # MRP value span follows the "M.R.P." label span; price may be in a child span
        elems = page_doc.xpath(
            "//span[contains(text(),'M.R.P')]/following-sibling::span[1]"
        )
        if elems:
            p = _extract_price("".join(elems[0].itertext()))
            if p:
                return p
        # Fallback: full text of the MRP container div
        for e in page_doc.xpath("//*[contains(text(),'M.R.P')]"):
            t = "".join(e.getparent().itertext()) if e.getparent() is not None else ""
            p = _extract_price(t)
            if p:
                return p
        return LimeroadComCommerceCrawl.get_selling_price(page_doc, inhash)

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        sell = LimeroadComCommerceCrawl.get_selling_price(page_doc, inhash)
        lst  = LimeroadComCommerceCrawl.get_list_price(page_doc, inhash)
        if sell and lst and lst > sell:
            return round((lst - sell) / lst * 100)
        return 0

    @staticmethod
    def get_sku(page_doc, inhash):
        d = _json_ld(page_doc)
        return d.get("productID") or None

    @staticmethod
    def get_color(page_doc, inhash):
        d = _json_ld(page_doc)
        desc = d.get("description", "")
        m = _re.search(r'color\s*:\s*([^,]+)', desc, _re.I)
        if m:
            return m.group(1).strip()
        return None

    @staticmethod
    def get_seller(page_doc, inhash):
        d = _json_ld(page_doc)
        return d.get("offers", {}).get("seller", {}).get("name") or None

    @staticmethod
    def get_description(page_doc, inhash):
        d = _json_ld(page_doc)
        return d.get("description") or None
