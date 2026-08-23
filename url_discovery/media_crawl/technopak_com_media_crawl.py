from sdf_module.url_discovery import *
from core.discovery_helpers import wordpress_pages
from urllib.parse import urljoin, urlparse
import logging
logger = logging.getLogger(__name__)

# technopak.com 301-redirects to tkc.in ("The Knowledge Company" -- Technopak's
# rebranded site). It's WordPress with /page/N/ pagination. The old
# /resources/ and /publications/ sections are gone; the insights blog now
# lives at /perspective/, with articles as flat top-level slugs
# (tkc.in/some-article-slug/). The other nav entries (fashion-lifestyle,
# retail-ecommerce, etc.) are portfolio/landing pages whose content is shown
# in on-page popups with no separate article URLs, so they're not usable as
# seeds for this crawl.
DOMAIN = "tkc.in"
SKIP_SEGMENTS = [
    'page', 'tag', 'author', 'category', 'search', 'feed', 'wp-content', 'wp-json',
    'perspective', 'fashion-lifestyle', 'retail-ecommerce', 'beauty-wellness', 'fmcg',
    'food-services', 'careers', 'contact', 'consumer-products-2', 'leadership',
    'private-equity', 'sustainability', 'travel-retail', 'who-we-are', 'alcoholic-beverages',
]


class TechnopakComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += wordpress_pages(keyurl, count=8)
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
                if len(parts) != 1:
                    continue
                if parts[0] in SKIP_SEGMENTS:
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
