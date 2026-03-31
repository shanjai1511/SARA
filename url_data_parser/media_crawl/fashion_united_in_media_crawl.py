from sdf_module.url_parser import *

class FashionUnitedInMediaCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            pass
        except Exception as e:
            print(f"Exception occurred: {e}")
        return final_data

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        formatted_datetime = current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
        return formatted_datetime

    @staticmethod
    def get_product_name(page_doc, inhash):
        return None

    @staticmethod
    def get_list_price(page_doc, inhash):
        return None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        return None
