from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin
import re

# nykaafashion.com blocks direct requests (403) — must go through unblock service (cffi strategy)

class NykaaFashionComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            connector = "&" if "?" in keyurl else "?"
            for p in range(2, 12):
                pagination_url.append(f"{keyurl}{connector}page={p}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url[:10]

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
                full = urljoin(url, href)
                if "nykaafashion.com" not in full:
                    continue
                if "/p/" not in full and "/product/" not in full:
                    continue
                # strip query params
                full = full.split("?")[0]
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
                rank += 1
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
