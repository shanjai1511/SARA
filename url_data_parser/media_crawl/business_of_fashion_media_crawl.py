from sdf_module.url_parser import *

class BusinessOfFashionMediaCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            # nothing to modify for media articles
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
        # use title meta or h1
        value = page_doc.xpath("//meta[contains(@property,'og:title')]/@content")
        if value:
            return value[0]
        title = page_doc.xpath("//h1/text()")
        return title[0].strip() if title else ""

    @staticmethod
    def get_list_price(page_doc, inhash):
        return None
    
    @staticmethod
    def get_selling_price(page_doc, inhash):
        return None

    @staticmethod
    def get_author_name(page_doc, inhash):
        # look for JSON-LD person name
        scripts = page_doc.xpath("//script[contains(text(),'@type\":\"Person\"')]/text()")
        if scripts:
            import re
            m = re.search(r'"name"\s*:\s*"([^"]+)"', scripts[0])
            if m:
                return m.group(1)
        # fallback to link with /author/
        author = page_doc.xpath("//a[contains(@href,'/author/')]/text()")
        return author[0].strip() if author else ""

    @staticmethod
    def get_post_date(page_doc, inhash):
        # try JSON-LD datePublished
        scripts = page_doc.xpath("//script[contains(text(),'datePublished')]/text()")
        if scripts:
            import re
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', scripts[0])
            if m:
                return m.group(1)
        # fallback to time tag text
        dt = page_doc.xpath("//time/text()")
        return dt[0].strip() if dt else ""

    @staticmethod
    def get_article_content(page_doc, inhash):
        paragraphs = page_doc.xpath("//article[contains(@class,'b-article-body')]//p/text()")
        content = ""
        for p in paragraphs:
            if p and p.strip():
                content += p.strip() + " "
        return content.strip()

    @staticmethod
    def get_image_url(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return value[0] if value else ""
