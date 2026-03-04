from sdf_module.url_parser import *

class VogueInMediaCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            url,category = str(inhash).split("|")
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
        value = sdfFetch.encode(inhash)
        return value

    @staticmethod
    def get_page_url(page_doc, inhash):
        return inhash.split("|")[0]

    @staticmethod
    def get_article_title(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'title')]/@content")    
        return value[0] if value else ""

    @staticmethod
    def get_sub_title(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'description')]/@content")
        return value[0] if value else ""
    
    @staticmethod
    def get_author_name(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'article:author')]/@content")
        return value[0] if value else ""
    
    @staticmethod
    def get_post_date(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'article:published_time')]/@content")
        return value[0] if value else ""
    
    @staticmethod
    def get_article_content(page_doc, inhash):
        value = page_doc.xpath("//div[contains(@class,'article__body')]/div/p")
        content = ""
        for i in value:
            if i is not None and i.text and i.text.strip():
                content += str(i.text.strip()) + " "
        return content if content else ""
    
    @staticmethod
    def get_image_url(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return value[0] if value else ""
