from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# Business of Fashion — heavily paywalled.
# Public listing pages at /articles/ and /news/ show article cards without login.
# We collect article URLs from listing pages; parser extracts what's visible (title, date, teaser).
class BusinessOfFashionMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            base = keyurl.rstrip("/")
            for i in range(2, 16):
                pagination_url.append(f"{base}?page={i}")
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

            # BoF article links: /articles/<slug> or /news/<slug>
            links = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            for link in links:
                full = urljoin("https://www.businessoffashion.com", link) if link.startswith("/") else link
                parsed = urlparse(full)
                if "businessoffashion.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                if not any(seg in path for seg in ["/articles/", "/news/"]):
                    continue
                parts = [p for p in path.strip("/").split("/") if p]
                # must have section + slug (at least 2 segments)
                if len(parts) < 2:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
