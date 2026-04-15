from sdf_module.url_parser import *
import logging
logger = logging.getLogger(__name__)

class StyleunionComCommerceCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            url,category = str(inhash).split("|")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return final_data

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        # Format the date and time in the desired format
        formatted_datetime = current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
        return formatted_datetime

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(f"{str(inhash)}")

    @staticmethod
    def get_page_url(page_doc, inhash):
        value = inhash.split("|")[0]
        return value

    @staticmethod
    def get_product_name(page_doc, inhash):
        elems = page_doc.xpath("//h1[contains(@class,'product__title')]")
        return elems[0].text.strip() if elems and elems[0].text else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        elems = page_doc.xpath("//span[contains(@class,'regular-price')]")
        if not elems or not elems[0].text:
            return None
        return int(re.sub(r"\D", "", elems[0].text.strip())) or None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        value = StyleunionComCommerceCrawl.get_list_price(page_doc, inhash)
        return value

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        value = 0
        return value
    
    @staticmethod
    def get_size(page_doc, inhash):
        elems = page_doc.xpath("//p[contains(@id,'variantSku')]/span")
        return elems[0].text.strip() if elems and elems[0].text else None

    @staticmethod
    def get_color(page_doc, inhash):
        elems = page_doc.xpath("//input[contains(@id,'main-product-Color')]/@value")
        return elems[0].strip() if elems else None
    
    @staticmethod
    def get_description(page_doc, inhash):
        elems = page_doc.xpath("//div[contains(@class,'desc_inner')]")
        texts = [" ".join(t.strip() for t in el.xpath(".//text()") if t.strip())
            for el in elems
        ]
        return " ".join(texts) if texts else None
    
    @staticmethod
    def get_sku(page_doc, inhash):
        elems = page_doc.xpath("//input[contains(@name,'sku_id')]/@value")
        return elems[0].strip() if elems else None
