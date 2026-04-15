from sdf_module.url_parser import *
import logging
logger = logging.getLogger(__name__)

class AmazonInCommerceCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            url, category = str(inhash).split("|")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
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
        return str(inhash).split("|")[0]

    @staticmethod
    def get_product_name(page_doc, inhash):
        elems = page_doc.xpath("//span[@id='productTitle']/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        elems = page_doc.xpath("//span[@class='a-price a-text-price a-size-medium']/span/text()")
        if elems:
            return int(re.sub(r"\D", "", elems[0]))
        return None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        elems = page_doc.xpath("//span[@id='priceblock_ourprice']/text()")
        if elems:
            return int(re.sub(r"\D", "", elems[0]))
        return None

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        # Amazon often shows savings in a span with id 'regularprice_savings'
        elems = page_doc.xpath("//td[@class='a-span12 a-color-price a-size-base']//text()")
        if elems:
            text = "".join(elems).strip()
            match = re.search(r"(\d+)%", text)
            if match:
                return int(match.group(1))
        return 0

    @staticmethod
    def get_size(page_doc, inhash):
        vals = page_doc.xpath("//span[@id='native_dropdown_selected_size_name']/text()")
        return vals[0].strip() if vals else None

    @staticmethod
    def get_color(page_doc, inhash):
        vals = page_doc.xpath("//span[@id='variation_color_name']//span[@class='selection']/text()")
        return vals[0].strip() if vals else None

    @staticmethod
    def get_description(page_doc, inhash):
        texts = page_doc.xpath("//div[@id='productDescription']//text()")
        return " ".join(t.strip() for t in texts if t.strip()) or None

    @staticmethod
    def get_sku(page_doc, inhash):
        vals = page_doc.xpath("//th[text()='ASIN']/following-sibling::td/text()")
        return vals[0].strip() if vals else None
