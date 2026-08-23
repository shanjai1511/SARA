from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse
import logging
logger = logging.getLogger(__name__)

# theverge.com no longer publishes a fashion/retail/ecommerce vertical at all
# (it's a general technology news + reviews site; the old /fashion/, /retail/
# and /ecommerce/ sections now 404). The closest still-live equivalent to a
# "retail" vertical is its consumer-tech shopping/deals coverage:
#   /shopping        - gadget deals and shopping roundups
#   /buying-guides    - "best of" buying guides
#   /gift-guides      - gift guides
# These use /<section>/archives/<page> pagination (not ?page=N or /page/N/).
DOMAIN = "theverge.com"
SKIP_SEGMENTS = ['page', 'archives', 'tag', 'author', 'category', 'search', 'feed', 'topic', 'video', 'gallery', 'photo', 'quiz', 'newsletter']


class TheVergeComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            base = keyurl.rstrip("/")
            for i in range(2, 10):
                pagination_url.append(f"{base}/archives/{i}")
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
                # The Verge article URLs are /<section>/<numeric-id>/<slug>
                if len(parts) < 3 or parts[0] in SKIP_SEGMENTS or not parts[1].isdigit():
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
