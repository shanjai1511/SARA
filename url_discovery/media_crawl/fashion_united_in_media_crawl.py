from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# fashionunited.in uses ?page=N querystring pagination
class FashionUnitedInMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            connector = "&" if "?" in keyurl else "?"
            for i in range(2, 16):
                pagination_url.append(f"{keyurl}{connector}page={i}")
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
                if "fashionunited.in" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                # FashionUnited India articles: /news/topic/headline-id/
                if "/news/" not in path:
                    continue
                parts = [p for p in path.strip("/").split("/") if p]
                if len(parts) < 3:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
