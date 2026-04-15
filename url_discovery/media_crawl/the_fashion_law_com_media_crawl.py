from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# The Fashion Law is WordPress — category pages paginate via /page/N/
_TFL_SKIP = {
    "category", "tag", "author", "page", "wp-content", "wp-includes",
    "wp-json", "feed", "search", "about", "contact", "subscribe",
    "advertise", "privacy", "terms", "cookie",
}


class TheFashionLawComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            base = keyurl.rstrip("/")
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

            # Prefer article-scoped links; fall back to all hrefs
            links = parsed_tree.xpath("//article//a[@href]/@href") or \
                    parsed_tree.xpath("//a[@href]/@href")

            seen = set()
            for link in links:
                full = urljoin(url, link)
                parsed = urlparse(full)
                if "thefashionlaw.com" not in parsed.netloc:
                    continue
                path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                if not path_parts:
                    continue
                if path_parts[0].lower() in _TFL_SKIP:
                    continue
                # TFL article slugs are a single path segment
                if len(path_parts) > 2:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
