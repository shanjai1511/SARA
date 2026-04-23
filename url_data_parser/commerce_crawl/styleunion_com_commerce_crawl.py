from sdf_module.url_parser import *
import logging
import re as _re
logger = logging.getLogger(__name__)


class StyleunionComCommerceCrawl():

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
        elems = page_doc.xpath("//h1[contains(@class,'product__title')]//text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        elems = page_doc.xpath(
            "//div[contains(@class,'product__info')]//span[contains(@class,'regular-price')]//text()"
            " | //div[contains(@class,'product__info')]//span[contains(@class,'compare-at-price')]//text()"
        )
        for e in elems:
            digits = _re.sub(r"\D", "", e.strip())
            if digits:
                return int(digits)
        return None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        elems = page_doc.xpath(
            "//div[contains(@class,'product__info')]//span[contains(@class,'sale-price')]//text()"
            " | //div[contains(@class,'product__info')]//span[contains(@class,'price-item--sale')]//text()"
        )
        for e in elems:
            digits = _re.sub(r"\D", "", e.strip())
            if digits:
                return int(digits)
        return StyleunionComCommerceCrawl.get_list_price(page_doc, inhash)

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        lp = StyleunionComCommerceCrawl.get_list_price(page_doc, inhash)
        sp = StyleunionComCommerceCrawl.get_selling_price(page_doc, inhash)
        if lp and sp and lp > sp:
            return round((lp - sp) / lp * 100)
        return None

    @staticmethod
    def get_color(page_doc, inhash):
        elems = page_doc.xpath(
            "//input[contains(@id,'main-product-Color') and @checked]/@value"
            " | //fieldset[contains(@id,'Color')]//input[@checked]/@value"
        )
        if elems:
            return elems[0].strip()
        elems = page_doc.xpath("//input[contains(@id,'main-product-Color')]/@value")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_size(page_doc, inhash):
        elems = page_doc.xpath("//p[contains(@id,'variantSku')]/span//text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_description(page_doc, inhash):
        elems = page_doc.xpath(
            "//div[contains(@class,'rte')]//text()"
            " | //div[contains(@class,'product__description')]//text()"
        )
        text = " ".join(e.strip() for e in elems if e.strip())
        return text or None

    @staticmethod
    def get_sku(page_doc, inhash):
        elems = page_doc.xpath("//input[contains(@name,'sku_id')]/@value")
        return elems[0].strip() if elems else None
