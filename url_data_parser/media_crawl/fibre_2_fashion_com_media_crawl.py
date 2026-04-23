from sdf_module.url_parser import *
import logging
import json as _json
import re as _re
logger = logging.getLogger(__name__)


def _jsonld(page_doc) -> dict:
    for s in page_doc.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            d = _json.loads(s)
            if d.get("@type") in ("Article", "NewsArticle", "BlogPosting"):
                return d
        except Exception:
            pass
    return {}


class Fibre2FashionComMediaCrawl():

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
        ld = _jsonld(page_doc)
        if ld.get("headline"):
            return ld["headline"].strip()
        elems = page_doc.xpath("//meta[contains(@property,'og:title')]/@content | //h1/text()")
        title = elems[0].strip() if elems else ""
        # strip site name suffix
        return _re.sub(r'\s*[-|]\s*Fibre2Fashion\s*$', '', title, flags=_re.IGNORECASE).strip()

    @staticmethod
    def get_sub_title(page_doc, inhash):
        elems = page_doc.xpath("//div[contains(@class,'panel-body')]//text()")
        text = " ".join(e.strip() for e in elems if e.strip())
        if text:
            return text[:500]
        elems2 = page_doc.xpath("//meta[contains(@property,'og:description')]/@content | //meta[@name='description']/@content")
        return elems2[0].strip() if elems2 else ""

    @staticmethod
    def get_author_name(page_doc, inhash):
        ld = _jsonld(page_doc)
        author = ld.get("author", "")
        if isinstance(author, dict):
            return author.get("name", "").strip()
        if isinstance(author, str) and author:
            return author.strip()
        elems = page_doc.xpath("//meta[contains(@property,'article:author')]/@content | //meta[@name='author']/@content")
        val = elems[0].strip() if elems else ""
        # skip if it's just the domain
        return val if val and "fibre2fashion.com" not in val else ""

    @staticmethod
    def get_post_date(page_doc, inhash):
        ld = _jsonld(page_doc)
        if ld.get("datePublished"):
            return ld["datePublished"]
        elems = page_doc.xpath("//meta[contains(@property,'article:published_time')]/@content | //time/@datetime")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_article_content(page_doc, inhash):
        elems = page_doc.xpath("//div[contains(@class,'articledetails2024')]//p//text()")
        return " ".join(e.strip() for e in elems if e.strip())

    @staticmethod
    def get_image_url(page_doc, inhash):
        elems = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return elems[0].strip() if elems else ""
