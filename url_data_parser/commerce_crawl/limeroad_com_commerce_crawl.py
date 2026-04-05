from sdf_module.url_parser import *

class LimeroadComCommerceCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
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
        return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)

    @staticmethod
    def get_product_name(page_doc, inhash):
        elems = page_doc.xpath("//meta[contains(@property,'og:title')]/@content | //h1/text()")
        value = " ".join(e.strip() for e in elems if e and e.strip()).strip()
        return value or None

    @staticmethod
    def get_list_price(page_doc, inhash):
        elems = page_doc.xpath(
            "//span[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mrp')]/text()"
            " | //span[contains(@class,'list')]/text()"
            " | //span[contains(@class,'old')]/text()"
        )
        if elems:
            val = int(re.sub(r"\D", "", elems[0]))
            return val if val else None
        return None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        elems = page_doc.xpath(
            "//span[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'price')]/text()"
            " | //span[contains(@class,'final')]/text()"
        )
        if elems:
            val = int(re.sub(r"\D", "", elems[0]))
            if val:
                return val
        return LimeroadComCommerceCrawl.get_list_price(page_doc, inhash)
