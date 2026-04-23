from sdf_module.url_parser import *
import logging
import json as _json
import re as _re
logger = logging.getLogger(__name__)


def _apollo(page_doc) -> dict:
    """Extract LocalNewsArticle from __NEXT_DATA__ apolloState."""
    for s in page_doc.xpath('//script[@id="__NEXT_DATA__"]/text()'):
        try:
            d = _json.loads(s)
            apollo = d.get("props", {}).get("pageProps", {}).get("apolloState", {})
            for k, v in apollo.items():
                if isinstance(v, dict) and v.get("__typename") == "LocalNewsArticle":
                    return v, apollo
        except Exception:
            pass
    return {}, {}


def _strip_html(text: str) -> str:
    return _re.sub(r"<[^>]+>", " ", text or "").strip()


class FashionUnitedGlobalComMediaCrawl():

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
        article, _ = _apollo(page_doc)
        if article.get("title"):
            return article["title"].strip()
        elems = page_doc.xpath("//meta[contains(@property,'og:title')]/@content | //h1/text()")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_sub_title(page_doc, inhash):
        article, _ = _apollo(page_doc)
        val = article.get("dek") or article.get("description") or ""
        if val:
            return _strip_html(val)
        elems = page_doc.xpath("//meta[contains(@property,'og:description')]/@content | //meta[@name='description']/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_author_name(page_doc, inhash):
        article, apollo = _apollo(page_doc)
        creator = article.get("creator", {})
        if isinstance(creator, dict):
            ref = creator.get("__ref", "")
            user = apollo.get(ref, {})
            if user.get("name"):
                return user["name"].strip()
        # fallback to meta
        elems = page_doc.xpath("//meta[contains(@property,'article:author')]/@content | //meta[@name='author']/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_post_date(page_doc, inhash):
        article, _ = _apollo(page_doc)
        if article.get("insertedAt"):
            return article["insertedAt"]
        elems = page_doc.xpath("//meta[@name='DC.date.issued']/@content | //meta[contains(@property,'article:published_time')]/@content")
        return elems[0].strip() if elems else ""

    @staticmethod
    def get_article_content(page_doc, inhash):
        article, _ = _apollo(page_doc)
        body_key = next((k for k in article if k.startswith("body")), None)
        body = _strip_html(article.get(body_key, "") or "")
        if body:
            return body
        elems = page_doc.xpath("//article//p//text()")
        return " ".join(e.strip() for e in elems if e and e.strip() and e.strip() != "loading...")

    @staticmethod
    def get_image_url(page_doc, inhash):
        article, _ = _apollo(page_doc)
        img_key = next((k for k in article if k.startswith("imageUrls")), None)
        imgs = article.get(img_key, [])
        if imgs:
            return imgs[0]
        elems = page_doc.xpath("//meta[contains(@property,'og:image')]/@content")
        return elems[0].strip() if elems else ""
