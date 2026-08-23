from sdf_module.url_parser import *
import logging
import json as _json
import re as _re

logger = logging.getLogger(__name__)


def _json_ld(page_doc) -> dict:
    """Return the first Product JSON-LD block on the page, or {}."""
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


def _list_price_from_html(page_doc, selling_price: int) -> int | None:
    """
    Flipkart embeds prices in combined text like '62%999₹378'.
    Find a container whose text contains {mrp}₹{selling_price} where mrp > selling_price.
    """
    sell_str = str(selling_price)
    pattern = _re.compile(
        r'(\d{3,})'           # MRP (3+ digits)
        r'[^\d]+'             # separator (₹ or similar)
        r'(?=.*?' + _re.escape(sell_str) + r')',
        _re.DOTALL,
    )
    for e in page_doc.xpath('//*[@class]'):
        t = "".join(e.itertext()).strip()
        if sell_str not in t or len(t) > 30:
            continue
        m = pattern.search(t)
        if m:
            mrp = int(m.group(1))
            if mrp > selling_price:
                return mrp
    return None


class FlipkartComCommerceCrawl():

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
            return d["name"]
        for h in page_doc.xpath("//h1"):
            t = "".join(h.itertext()).strip()
            if t:
                return t
        return None

    @staticmethod
    def get_brand(page_doc, inhash):
        d = _json_ld(page_doc)
        brand = d.get("brand", {})
        return brand.get("name") if isinstance(brand, dict) else None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        d = _json_ld(page_doc)
        offers = d.get("offers", {})
        if isinstance(offers, dict) and offers.get("price"):
            return int(offers["price"])
        if isinstance(offers, list) and offers:
            p = offers[0].get("price")
            if p:
                return int(p)
        return None

    @staticmethod
    def get_list_price(page_doc, inhash):
        sell = FlipkartComCommerceCrawl.get_selling_price(page_doc, inhash)
        if sell:
            mrp = _list_price_from_html(page_doc, sell)
            if mrp:
                return mrp
        return sell  # fallback: list = sell when no MRP found

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        sell = FlipkartComCommerceCrawl.get_selling_price(page_doc, inhash)
        lst  = FlipkartComCommerceCrawl.get_list_price(page_doc, inhash)
        if sell and lst and lst > sell:
            return round((lst - sell) / lst * 100)
        return 0

    @staticmethod
    def get_rating(page_doc, inhash):
        d = _json_ld(page_doc)
        ar = d.get("aggregateRating", {})
        if isinstance(ar, dict) and ar.get("ratingValue"):
            return float(ar["ratingValue"])
        return None

    @staticmethod
    def get_num_reviews(page_doc, inhash):
        d = _json_ld(page_doc)
        ar = d.get("aggregateRating", {})
        if isinstance(ar, dict):
            return ar.get("ratingCount") or ar.get("reviewCount") or None
        return None

    @staticmethod
    def get_sku(page_doc, inhash):
        d = _json_ld(page_doc)
        return d.get("sku") or None

    @staticmethod
    def get_color(page_doc, inhash):
        d = _json_ld(page_doc)
        return d.get("color") or None

    @staticmethod
    def get_description(page_doc, inhash):
        # Flipkart's og:description has a generic template, prefer page content
        for e in page_doc.xpath('//div[contains(@class,"_1mXcCf")]//text() | //div[@class="RmoJbe"]//text()'):
            t = e.strip()
            if t and len(t) > 30:
                return t
        d = _json_ld(page_doc)
        return d.get("description") or None
