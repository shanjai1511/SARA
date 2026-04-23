from sdf_module.url_parser import *
import logging
import json as _json
logger = logging.getLogger(__name__)


def _jsonld(page_doc) -> dict:
    for s in page_doc.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            d = _json.loads(s)
            if d.get("@type") in ("NewsArticle", "Article"):
                return d
        except Exception:
            pass
    return {}


class BusinessOfFashionMediaCrawl():

    @staticmethod
    def modify_page_doc(inhash, page_doc):
        return []

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        return current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)

    @staticmethod
    def get_article_title(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("headline"):
            return ld["headline"].strip()
        value = page_doc.xpath("//meta[contains(@property,'og:title')]/@content | //h1/text()")
        return value[0].strip() if value else ""

    @staticmethod
    def get_sub_title(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("description"):
            return ld["description"].strip()
        value = page_doc.xpath("//meta[contains(@property,'og:description')]/@content | //meta[@name='description']/@content")
        return value[0].strip() if value else ""

    @staticmethod
    def get_author_name(page_doc, inhash):
        ld = _jsonld(page_doc)
        authors = ld.get("author", [])
        if isinstance(authors, dict):
            authors = [authors]
        if authors:
            return ", ".join(a.get("name", "") for a in authors if a.get("name"))
        author = page_doc.xpath("//a[contains(@href,'/author/')]/text() | //a[contains(@href,'/authors/')]/text()")
        return author[0].strip() if author else ""

    @staticmethod
    def get_post_date(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("datePublished"):
            return ld["datePublished"]
        dt = page_doc.xpath("//time/@datetime | //time/text()")
        return dt[0].strip() if dt else ""

    @staticmethod
    def get_article_content(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("articleBody") and len(ld["articleBody"]) > 100:
            return ld["articleBody"].strip()
        paras = page_doc.xpath("//article//p/text() | //div[contains(@class,'article-body')]//p/text()")
        return " ".join(p.strip() for p in paras if p and p.strip())

    @staticmethod
    def get_image_url(page_doc, inhash):
        value = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return value[0] if value else ""
