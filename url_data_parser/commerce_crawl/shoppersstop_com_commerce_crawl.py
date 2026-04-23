from sdf_module.url_parser import *
import logging
import json as _json
import re as _re
logger = logging.getLogger(__name__)


def _next_data(page_doc) -> dict:
    for s in page_doc.xpath('//script[@id="__NEXT_DATA__"]/text()'):
        try:
            return _json.loads(s)
        except Exception:
            pass
    return {}


def _product_item(page_doc) -> dict:
    """Extract product item from pdpData.data.products.items[0]."""
    data = _next_data(page_doc)
    if not data:
        return {}
    try:
        items = (
            data["props"]["pageProps"]["pdpData"]["data"]["products"]["items"]
        )
        if items:
            return items[0]
    except (KeyError, TypeError, IndexError):
        pass
    return {}


def _mrp(item: dict):
    """MRP lives in variants[].product.price_range since parent regular_price is often null."""
    pr = item.get("price_range", {}).get("minimum_price", {})
    reg = pr.get("regular_price", {}).get("value")
    if reg:
        try:
            return int(float(reg))
        except Exception:
            pass
    for v in item.get("variants", []):
        vpr = v.get("product", {}).get("price_range", {}).get("minimum_price", {})
        val = vpr.get("regular_price", {}).get("value")
        if val:
            try:
                return int(float(val))
            except Exception:
                pass
    return None


def _selling_price(item: dict):
    pr = item.get("price_range", {}).get("minimum_price", {})
    val = pr.get("final_price", {}).get("value")
    if val is not None:
        try:
            return int(float(val))
        except Exception:
            pass
    return None


class ShoppersstopComCommerceCrawl():

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
        p = _product_item(page_doc)
        return (p.get("name") or "").strip() or None

    @staticmethod
    def get_brand(page_doc, inhash):
        p = _product_item(page_doc)
        return (p.get("brand_info") or p.get("brand_name") or "").strip() or None

    @staticmethod
    def get_sku(page_doc, inhash):
        p = _product_item(page_doc)
        return str(p.get("sku") or "")

    @staticmethod
    def get_list_price(page_doc, inhash):
        return _mrp(_product_item(page_doc))

    @staticmethod
    def get_selling_price(page_doc, inhash):
        p = _product_item(page_doc)
        sp = _selling_price(p)
        if sp is not None:
            return sp
        return _mrp(p)

    @staticmethod
    def get_rating(page_doc, inhash):
        p = _product_item(page_doc)
        val = p.get("rating_summary")
        if val is not None:
            try:
                return round(float(val), 1)
            except Exception:
                pass
        return None

    @staticmethod
    def get_image_url(page_doc, inhash):
        p = _product_item(page_doc)
        imgs = p.get("additional_images", [])
        if imgs and isinstance(imgs[0], dict):
            return imgs[0].get("url", "")
        img = p.get("image", {})
        if isinstance(img, dict):
            return img.get("url", "")
        return ""
