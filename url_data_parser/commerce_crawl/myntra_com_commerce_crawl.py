from sdf_module.url_parser import *
import logging
import json as _json
import re as _re
logger = logging.getLogger(__name__)


def _pdp_data(page_doc) -> dict:
    """Extract pdpData from window.__myx embedded in the page."""
    scripts = page_doc.xpath('//script[contains(text(),"__myx")]/text()')
    for s in scripts:
        idx = s.find('window.__myx = {')
        if idx < 0:
            idx = s.find('window.__myx={')
        if idx < 0:
            continue
        start = s.index('{', idx)
        depth = 0
        for i, c in enumerate(s[start:]):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(s[start:start + i + 1]).get('pdpData', {})
                    except Exception:
                        return {}
    return {}


def _json_ld(page_doc) -> dict:
    for s in page_doc.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            d = _json.loads(s)
            if isinstance(d, dict) and d.get('@type') == 'Product':
                return d
        except Exception:
            pass
    return {}


class MyntraComCommerceCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        return []

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        return current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)

    @staticmethod
    def get_product_name(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        name = pdp.get('name')
        if name:
            return name.strip()
        jld = _json_ld(page_doc)
        return jld.get('name') or None

    @staticmethod
    def get_brand(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        brand = pdp.get('brand', {})
        if isinstance(brand, dict):
            return brand.get('name') or None
        jld = _json_ld(page_doc)
        b = jld.get('brand', {})
        return b.get('name') if isinstance(b, dict) else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        price = pdp.get('price', {})
        if isinstance(price, dict) and price.get('mrp'):
            try:
                return int(price['mrp'])
            except Exception:
                pass
        mrp = pdp.get('mrp')
        if mrp:
            try:
                return int(mrp)
            except Exception:
                pass
        jld = _json_ld(page_doc)
        hp = jld.get('offers', {}).get('highPrice')
        if hp:
            try:
                return int(hp)
            except Exception:
                pass
        return None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        price = pdp.get('price', {})
        if isinstance(price, dict) and price.get('discounted'):
            try:
                return int(price['discounted'])
            except Exception:
                pass
        jld = _json_ld(page_doc)
        sp = jld.get('offers', {}).get('price')
        if sp:
            try:
                return int(float(sp))
            except Exception:
                pass
        return MyntraComCommerceCrawl.get_list_price(page_doc, inhash)

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        mrp = MyntraComCommerceCrawl.get_list_price(page_doc, inhash)
        sp = MyntraComCommerceCrawl.get_selling_price(page_doc, inhash)
        if mrp and sp and mrp > sp:
            return round((mrp - sp) / mrp * 100)
        return None

    @staticmethod
    def get_rating(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        ratings = pdp.get('ratings', {})
        if isinstance(ratings, dict):
            val = ratings.get('averageRating')
            if val:
                try:
                    return round(float(val), 1)
                except Exception:
                    pass
        return None

    @staticmethod
    def get_num_reviews(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        ratings = pdp.get('ratings', {})
        if isinstance(ratings, dict):
            cnt = ratings.get('totalCount')
            if cnt:
                try:
                    return int(cnt)
                except Exception:
                    pass
        return None

    @staticmethod
    def get_sku(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        pid = pdp.get('id')
        if pid:
            return str(pid)
        jld = _json_ld(page_doc)
        return jld.get('sku') or None

    @staticmethod
    def get_color(page_doc, inhash):
        pdp = _pdp_data(page_doc)
        return pdp.get('baseColour') or None
