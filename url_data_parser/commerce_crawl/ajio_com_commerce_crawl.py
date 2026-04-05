from sdf_module.url_parser import *
import json
from urllib.parse import urljoin

class AjioComCommerceCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            # inhash is typically "url|{category_dict_as_string}"
            if isinstance(inhash, str) and "|" in inhash:
                url, category = inhash.split("|", 1)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return final_data

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
        return formatted_datetime

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        if isinstance(inhash, str) and "|" in inhash:
            return inhash.split("|", 1)[0]
        return str(inhash)

    @staticmethod
    def _extract_ld_json(page_doc):
        scripts = page_doc.xpath("//script[@type='application/ld+json']/text()")
        for raw in scripts or []:
            raw = (raw or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if isinstance(data, dict):
                yield data
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        yield item

    @staticmethod
    def get_product_name(page_doc, inhash):
        try:
            # Common Ajio layout: product title split across h1/h2 in some templates
            elems = page_doc.xpath("//h1[contains(@class,'prod-name')]/text() | //h1/text()")
            name = " ".join(e.strip() for e in elems if e and e.strip()).strip()
            if name:
                return name
        except Exception:
            pass

        try:
            for obj in AjioComCommerceCrawl._extract_ld_json(page_doc):
                if obj.get("@type") in ("Product", "product") and obj.get("name"):
                    return str(obj.get("name")).strip() or None
        except Exception:
            pass
        return None

    @staticmethod
    def get_list_price(page_doc, inhash):
        # Prefer MRP/list price; fallback to selling price if only one is present
        try:
            elems = page_doc.xpath(
                "//span[contains(@class,'prod-cp')]/text()"
                " | //span[contains(@class,'prod-mrp')]/text()"
                " | //span[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mrp')]/text()"
            )
            if elems:
                val = int(re.sub(r"\D", "", elems[0]))
                return val if val else None
        except Exception:
            pass

        try:
            for obj in AjioComCommerceCrawl._extract_ld_json(page_doc):
                offers = obj.get("offers") if isinstance(obj.get("offers"), (dict, list)) else None
                if isinstance(offers, dict):
                    price = offers.get("price")
                    if price is not None:
                        return int(float(str(price)))
                if isinstance(offers, list):
                    for off in offers:
                        if isinstance(off, dict) and off.get("price") is not None:
                            return int(float(str(off.get("price"))))
        except Exception:
            pass
        return None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        try:
            elems = page_doc.xpath(
                "//span[contains(@class,'prod-sp')]/text()"
                " | //span[contains(@class,'prod-selling-price')]/text()"
                " | //span[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'selling')]/text()"
            )
            if elems:
                val = int(re.sub(r"\D", "", elems[0]))
                return val if val else None
        except Exception:
            pass

        # Fallback: if only one price is available, treat it as selling price.
        return AjioComCommerceCrawl.get_list_price(page_doc, inhash)
