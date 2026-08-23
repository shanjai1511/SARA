from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin, urlparse
import re
import logging
logger = logging.getLogger(__name__)

DOMAIN = "yourstory.com"
# yourstory.com stopped using /story/ and /company/ prefixes -- articles now
# live at a date-based path, /<YYYY>/<M or MM>/<slug>, e.g.
#   /2025/11/flipkart-myntra-cbo-sharon-pais-fashion-business-meesho-competition
# The old ARTICLE_PATHS substring check never matched that shape, so every
# link on the tag page was discarded.
ARTICLE_PATH_RE = re.compile(r'^(19|20)\d{2}/(0?[1-9]|1[0-2])/.+')


class YourstoryComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += querystring_pages(keyurl, param="page", start=2, count=10)
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
                p    = urlparse(full)
                if DOMAIN not in p.netloc:
                    continue
                path = p.path.strip("/")
                if not ARTICLE_PATH_RE.match(path):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
