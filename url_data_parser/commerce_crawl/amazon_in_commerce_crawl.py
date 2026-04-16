from sdf_module.url_parser import *
import logging
import re as _re
logger = logging.getLogger(__name__)


def _price_from_block(page_doc):
    """Extract (selling_price_paise, list_price_paise) from the _price span."""
    elems = page_doc.xpath("//span[@id='_price'][1]")
    if elems:
        text = elems[0].text_content()
        prices = _re.findall(r'[\u20b9Rs\.]+\s*([\d,]+(?:\.\d+)?)', text)
        if len(prices) >= 2:
            sell = int(float(prices[0].replace(",", "")))
            lst  = int(float(prices[1].replace(",", "")))
            return sell, lst
        if len(prices) == 1:
            sell = int(float(prices[0].replace(",", "")))
            return sell, None
    return None, None


class AmazonInCommerceCrawl():

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
        return str(inhash).split("|")[0]

    @staticmethod
    def get_product_name(page_doc, inhash):
        # Mobile layout: title inside <h1> under title_feature_div
        elems = page_doc.xpath("//div[@id='title_feature_div']//h1//text()")
        if not elems:
            # Desktop fallback
            elems = page_doc.xpath("//span[@id='productTitle']/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        _, lst = _price_from_block(page_doc)
        if lst is not None:
            return lst
        # Desktop fallback
        elems = page_doc.xpath("//span[@class='a-price a-text-price']//span[@class='a-offscreen']/text()")
        if elems:
            return int(float(_re.sub(r"[^\d.]", "", elems[0])))
        return None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        sell, _ = _price_from_block(page_doc)
        if sell is not None:
            return sell
        # Desktop fallback
        elems = page_doc.xpath("//span[contains(@class,'a-price-whole')]/text()")
        if elems:
            return int(_re.sub(r"\D", "", elems[0]))
        return None

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        sell, lst = _price_from_block(page_doc)
        if sell and lst and lst > sell:
            return round((lst - sell) / lst * 100)
        # Inline badge fallback
        elems = page_doc.xpath("//span[contains(@class,'savingsPercentage')]/text()")
        if elems:
            m = _re.search(r"(\d+)", elems[0])
            if m:
                return int(m.group(1))
        return 0

    @staticmethod
    def get_size(page_doc, inhash):
        # Mobile: inline-twister dimension title
        vals = page_doc.xpath("//span[contains(@id,'size_name')]//text()")
        if vals:
            v = vals[0].strip()
            if v and v not in ("Make a size selection",):
                return v
        # Desktop dropdown fallback
        vals = page_doc.xpath("//span[@id='native_dropdown_selected_size_name']/text()")
        return vals[0].strip() if vals else None

    @staticmethod
    def get_color(page_doc, inhash):
        vals = page_doc.xpath("//span[contains(@id,'color_name')]//text()")
        if vals:
            v = vals[0].strip()
            if v and v not in ("Make a colour selection",):
                return v
        # Desktop variation fallback
        vals = page_doc.xpath("//span[@id='variation_color_name']//span[@class='selection']/text()")
        return vals[0].strip() if vals else None

    @staticmethod
    def get_description(page_doc, inhash):
        texts = page_doc.xpath("//div[@id='productDescription']//text()")
        result = " ".join(t.strip() for t in texts if t.strip())
        if result:
            return result
        # Feature bullets fallback
        texts = page_doc.xpath("//div[@id='feature-bullets']//li/span[@class='a-list-item']/text()")
        return " | ".join(t.strip() for t in texts if t.strip()) or None

    @staticmethod
    def get_sku(page_doc, inhash):
        vals = page_doc.xpath("//th[contains(text(),'ASIN')]/following-sibling::td/text()")
        return vals[0].strip() if vals else None

    @staticmethod
    def get_brand(page_doc, inhash):
        # Product overview table
        vals = page_doc.xpath("//tr[th[contains(text(),'Brand')]]/td//text()")
        if vals:
            return vals[0].strip()
        vals = page_doc.xpath("//a[@id='bylineInfo']/text()")
        if vals:
            return vals[0].strip().removeprefix("Visit the ").removeprefix("Brand: ")
        return None

    @staticmethod
    def get_rating(page_doc, inhash):
        vals = page_doc.xpath("//i[contains(@class,'a-icon-star')]//span[@class='a-icon-alt']/text()")
        if vals:
            m = _re.search(r"([\d.]+)", vals[0])
            if m:
                return float(m.group(1))
        return None

    @staticmethod
    def get_num_reviews(page_doc, inhash):
        vals = page_doc.xpath("//a[@id='acrCustomerReviewLink']/text()")
        for v in vals:
            m = _re.search(r"([\d,]+)", v)
            if m:
                return int(m.group(1).replace(",", ""))
        return None
