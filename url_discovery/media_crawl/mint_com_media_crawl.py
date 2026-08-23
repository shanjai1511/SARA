from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin, urlparse
import logging
import re as _re
logger = logging.getLogger(__name__)

# livemint.com dropped the /fashion and /companies/retail sections it used to
# have. Fashion coverage moved to /topic/fashion (mostly linking into
# /mint-lounge/style/...) and retail coverage moved to /industry/retail/...
# Article URLs on livemint always end with a long numeric id, e.g.
# "...-11787306595784.html" -- that's a much more reliable "is this an
# article" signal than matching on section path, since topic/listing pages
# link out across many unrelated sections too. Note: ?page=N is a no-op on
# these listing pages (every page returns the same fixed set), so depth1
# just passes the seed through like the sibling livemint_com config does.
DOMAIN = "livemint.com"
ARTICLE_RE = _re.compile(r"-\d{8,}\.html$")


class MintComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += querystring_pages(keyurl, param="page", start=2, count=3)
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
                if not ARTICLE_RE.search(p.path):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
