from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# just-style.com article paths include: /news/, /analysis/, /comment/, /data/
_ARTICLE_PATHS = ["/news/", "/analysis/", "/comment/", "/data/", "/research/"]
_SKIP_PATHS = {
    "page", "tag", "author", "category", "wp-content", "wp-includes",
    "wp-json", "feed", "search", "about", "contact", "subscribe",
    "advertise", "privacy", "terms", "cookie",
}


class JustStyleComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            base = keyurl.rstrip("/")
            # just-style uses WordPress /page/N/ format
            for i in range(2, 16):
                pagination_url.append(f"{base}/page/{i}/")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            links = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            for link in links:
                full = urljoin(url, link)
                parsed = urlparse(full)
                if "just-style.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                parts = [p for p in path.strip("/").split("/") if p]
                if not parts:
                    continue
                if parts[0] in _SKIP_PATHS:
                    continue
                # must be under a known article section
                if not any(seg in path for seg in _ARTICLE_PATHS):
                    continue
                # must have at least 2 segments (section/slug)
                if len(parts) < 2:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
