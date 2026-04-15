from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse
class LimeroadComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            connector = "&" if "?" in keyurl else "?"
            for p in range(2, 12):
                pagination_url.append(f"{keyurl}{connector}page={p}")
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
            hrefs = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            rank = 1
            for href in hrefs:
                if not href:
                    continue
                full = urljoin(url, href)
                parsed = urlparse(full)
                if "limeroad.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                # Limeroad product URLs: /product-name/story/<id> or /p/<id>
                if "/story/" not in path and "/p/" not in path and "/product/" not in path:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
                rank += 1
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
