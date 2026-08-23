from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# Fibre2Fashion uses numeric path-segment pagination:
#   /industry-article/fashion/  →  /industry-article/fashion/1/  /industry-article/fashion/2/  ...
class Fibre2FashionComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            base = keyurl.rstrip("/")
            # seed is page 0 (no suffix); pages 1-15 via numeric suffix
            for i in range(1, 16):
                pagination_url.append(f"{base}/{i}/")
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
                if "fibre2fashion.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                # F2F article paths: /industry-article/<id>/<slug>/
                if "/industry-article/" not in path:
                    continue
                parts = [p for p in path.strip("/").split("/") if p]
                # need: industry-article / <numeric-id> / <slug> = 3 parts, 2nd is digit
                if len(parts) < 3 or not parts[1].isdigit():
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
