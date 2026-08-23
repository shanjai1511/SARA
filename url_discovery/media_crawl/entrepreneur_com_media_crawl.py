from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse
import re
import logging
logger = logging.getLogger(__name__)

DOMAIN = "entrepreneur.com"
# entrepreneur.com articles are no longer under /article/ or /slideshow/ --
# the current pattern is /<category>/<slug>/<numeric-id>, e.g.
#   /starting-a-business/how-to-choose-the-right-business-model/481564
# The old ARTICLE_PATHS substring check never matched that shape, so 0
# articles were ever kept. Pagination is also path-based (/topic/x/page/N),
# not a "?page=N" query string -- the real pagination links are right there
# in the page markup (e.g. /topic/fashion/page/2).
ARTICLE_ID_RE = re.compile(r'^\d+$')
SKIP_SEGMENTS = ['page', 'tag', 'author', 'category', 'search', 'feed', 'topic', 'video',
                 'gallery', 'photo', 'quiz', 'newsletter']


class EntrepreneurComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            base = keyurl.rstrip("/")
            for i in range(2, 11):
                pagination_url.append(f"{base}/page/{i}")
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
                if len(parts) < 3:
                    continue
                if parts[0] in SKIP_SEGMENTS:
                    continue
                if not ARTICLE_ID_RE.match(parts[-1]):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
