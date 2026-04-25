from sdf_module.url_parser import *

class TechcrunchComMediaCrawl():

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        current_datetime = datetime.now()
        return current_datetime.strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return str(inhash)

    @staticmethod
    def get_article_title(page_doc, inhash):
        # Generic og:title works for most sites — override with site-specific XPath if needed
        elems = page_doc.xpath("//meta[@property='og:title']/@content | //h1/text()")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_sub_title(page_doc, inhash):
        elems = page_doc.xpath("//meta[@property='og:description']/@content | //meta[@name='description']/@content")
        return elems[0].strip() if elems else None

    @staticmethod
    def get_author_name(page_doc, inhash):
        elems = page_doc.xpath(
            "//meta[@property='article:author']/@content"
            " | //meta[@name='author']/@content"
            " | //a[@rel='author']/text()"
            " | //span[contains(@class,'author')]/text()"
        )
        return elems[0].strip() if elems else None

    @staticmethod
    def get_post_date(page_doc, inhash):
        elems = page_doc.xpath(
            "//meta[@property='article:published_time']/@content"
            " | //time/@datetime"
            " | //time/text()"
        )
        return elems[0].strip() if elems else None

    @staticmethod
    def get_article_content(page_doc, inhash):
        # TODO: narrow the XPath to this site's article body class for cleaner text
        elems = page_doc.xpath("//article//p//text() | //div[contains(@class,'article-body')]//p//text()")
        return " ".join(e.strip() for e in elems if e.strip()) or None

    @staticmethod
    def get_image_url(page_doc, inhash):
        elems = page_doc.xpath("//meta[@property='og:image']/@content")
        return elems[0] if elems else None
