from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin, urlparse
import re
import logging
logger = logging.getLogger(__name__)

DOMAIN = "businessinsider.com"
# Business Insider no longer nests articles under /retail/, /ecommerce/ or
# /fashion/ -- they are flat, single-path-segment slugs at the domain root
# that end in a "-YYYY-M[M]" publish-date suffix, e.g.
#   /mcdonalds-value-menu-slows-us-sales-ceo-assesses-impact-2026-8
# The old ARTICLE_PATHS substring check (looking for "/retail/" etc. inside
# the URL) and the "len(parts) < 2" guard both assumed a nested path this
# site no longer uses, so every real article link was being discarded and
# nav/section links (which also don't match) were the only candidates left.
ARTICLE_SLUG_RE = re.compile(r'-(19|20)\d{2}(-\d{1,2})?$')


class BusinessInsiderComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += querystring_pages(keyurl, param="page", start=2, count=8)
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
                if not ARTICLE_SLUG_RE.search(parts[0]):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
