from sdf_module.url_parser import *

class HouseOfMasabaComCommerceCrawl():

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        return current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return str(inhash)

    @staticmethod
    def get_product_name(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//h1[@class='pdp-title']/text() | //h1/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_list_price(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//*[contains(@class,'mrp')]//text() | //*[contains(@class,'list-price')]//text()")
        val = elems[0].strip() if elems else None
        if val:
            val = ''.join(c for c in val if c.isdigit())
        return int(val) if val else None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//*[contains(@class,'selling-price')]//text() | //*[contains(@class,'price')]//text()")
        val = elems[0].strip() if elems else None
        if val:
            val = ''.join(c for c in val if c.isdigit())
        return int(val) if val else None

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        # TODO: update XPath for this site
        elems = page_doc.xpath("//*[contains(@class,'discount')]//text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_size(page_doc, inhash):
        # TODO: update XPath — list of available sizes
        elems = page_doc.xpath("//*[contains(@class,'size-button')]//text()")
        return ", ".join(e.strip() for e in elems if e.strip()) or None

    @staticmethod
    def get_color(page_doc, inhash):
        elems = page_doc.xpath("//*[contains(@class,'color')]/@title | //*[contains(@class,'color')]//text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_description(page_doc, inhash):
        elems = page_doc.xpath("//*[contains(@class,'description')]//text()")
        return " ".join(e.strip() for e in elems if e.strip()) or None

    @staticmethod
    def get_sku(page_doc, inhash):
        elems = page_doc.xpath("//*[contains(@class,'sku')]//text() | //meta[@name='sku']/@content")
        return elems[0].strip() if elems else None
