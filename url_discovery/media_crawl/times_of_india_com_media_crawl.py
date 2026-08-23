from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin, urlparse
import logging
logger = logging.getLogger(__name__)

DOMAIN        = "timesofindia.indiatimes.com"
ARTICLE_PATHS = ['/articleshow/']
SKIP_SEGMENTS = ['page', 'tag', 'author', 'category', 'search', 'feed', 'topic', 'video', 'gallery', 'photo', 'quiz', 'newsletter']


class TimesOfIndiaComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += querystring_pages(keyurl, param="curpg", start=2, count=10)
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
                parts = [s for s in p.path.strip("/").split("/") if s]
                if len(parts) < 2:
                    continue
                if parts[0] in SKIP_SEGMENTS:
                    continue
                if ARTICLE_PATHS and not any(ap in full for ap in ARTICLE_PATHS):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
