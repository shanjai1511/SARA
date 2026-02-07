from sdf_module.url_parser import *

class StyleunionComInternalFeasibility():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            url,category = str(inhash).split("|")
        except Exception as e:
            print(f"Exception occurred: e")
        return final_data

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        # Format the date and time in the desired format
        formatted_datetime = current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]
        return formatted_datetime

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return

    @staticmethod
    def get_page_url(page_doc, inhash):
        return value

    @staticmethod
    def get_product_name(page_doc, inhash):
        return value

    @staticmethod
    def get_list_price(page_doc, inhash):
        return value
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        return value

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        return value
    
    @staticmethod
    def get_size(page_doc, inhash):
        return value
    
    @staticmethod
    def get_color(page_doc, inhash):
        return value
    
    @staticmethod
    def get_description(page_doc, inhash):
        return value
    
    @staticmethod
    def get_sku(page_doc, inhash):
        return value
