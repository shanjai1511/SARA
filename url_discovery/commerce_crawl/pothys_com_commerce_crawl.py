from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin
import logging
logger = logging.getLogger(__name__)

DOMAIN = "https://www.pothys.com"
PRODUCT_PATTERNS = ['/product/', '/p/']


class PothysComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            pagination_url = querystring_pages(
                keyurl, param="page", start=1, count=20
            )
        except Exception as e:
            logger.warning("Exception: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No DOM")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            seen = set()
            for href in parsed_tree.xpath("//a[@href]/@href"):
                full = urljoin(url, href)
                if DOMAIN not in full:
                    continue
                if not any(p in full for p in PRODUCT_PATTERNS):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
