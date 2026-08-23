from sdf_module.url_parser import *
import logging
import re as _re
logger = logging.getLogger(__name__)


class WwdComMediaCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        return []

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        return datetime.now().strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)

    @staticmethod
    def get_article_title(page_doc, inhash):
        elems = page_doc.xpath("//h1/text()")
        if not elems:
            elems = page_doc.xpath("//meta[contains(@property,'og:title')]/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_sub_title(page_doc, inhash):
        elems = page_doc.xpath("//meta[contains(@property,'og:description')]/@content | //meta[@name='description']/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_author_name(page_doc, inhash):
        elems = page_doc.xpath("//meta[contains(@property,'article:author')]/@content | //meta[@name='author']/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_post_date(page_doc, inhash):
        # avoid //time/@datetime which returns a template placeholder on WWD
        elems = page_doc.xpath("//meta[contains(@property,'article:published_time')]/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_article_content(page_doc, inhash):
        elems = page_doc.xpath("//article//p//text()")
        return " ".join(e.strip() for e in elems if e and e.strip())

    @staticmethod
    def get_image_url(page_doc, inhash):
        elems = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return elems[0].strip() if elems else ""
