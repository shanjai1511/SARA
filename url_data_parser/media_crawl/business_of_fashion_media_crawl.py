from sdf_module.url_parser import *
import logging
logger = logging.getLogger(__name__)

class BusinessOfFashionMediaCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        final_data = []
        try:
            if isinstance(inhash, str) and "|" in inhash:
                url, category = inhash.split("|", 1)
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
        return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)

    @staticmethod
    def get_article_title(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'og:title')]/@content | //h1/text()")
        return value[0].strip() if value else ""

    @staticmethod
    def get_sub_title(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'og:description')]/@content | //meta[@name='description']/@content")
        return value[0].strip() if value else ""

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
