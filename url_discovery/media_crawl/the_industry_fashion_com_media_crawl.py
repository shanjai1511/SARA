from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# theindustry.fashion — Oxygen/WordPress CMS
# Article URLs are bare slugs: theindustry.fashion/some-article-title/
_SKIP_PATHS = {
    "page", "tag", "author", "category", "wp-content", "wp-includes",
    "wp-json", "feed", "search", "about", "contact", "advertise",
    "subscribe", "privacy", "terms", "news", "analysis", "comment",
    "insight", "features", "market-data", "intelligence", "the-insider",
    "awards", "summit", "partner-with-us", "ads", "sample-page",
}


class TheIndustryFashionComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
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
            links = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            for link in links:
                full = urljoin(url, link)
                parsed = urlparse(full)
                if "theindustry.fashion" not in parsed.netloc:
                    continue
                parts = [p for p in parsed.path.strip("/").split("/") if p]
                # article slugs are exactly one path segment
                if len(parts) != 1:
                    continue
                if parts[0].lower() in _SKIP_PATHS:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
