from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# apparelresources.com is WordPress — pagination uses /page/N/ path format
class ApparelResourcesComMediaCrawl():

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
            dom = sdfFetch.get_page_content_hash(url, extended_header={"Accept-Encoding": "gzip, deflate"})
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            links = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            skip = {"page", "tag", "author", "category", "wp-content", "wp-includes", "feed", "search", "top-news"}
            for link in links:
                full = urljoin(url, link)
                parsed = urlparse(full)
                if "apparelresources.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                parts = [p for p in path.strip("/").split("/") if p]
                if not parts or parts[0] in skip:
                    continue
                # Articles: /section/sub-section/article-slug/ (3+ parts)
                if len(parts) < 3:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
