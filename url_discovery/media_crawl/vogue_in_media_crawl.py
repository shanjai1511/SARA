from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

# vogue.in — Conde Nast CMS, uses ?page=N; blocks scrapers so proxy needed
class VogueInMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            connector = "&" if "?" in keyurl else "?"
            for i in range(2, 11):
                pagination_url.append(f"{keyurl}{connector}page={i}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url, proxy="webshare_proxy")
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            if parsed_tree is None:
                raise Exception("Parsing failed")
            # Conde Nast article links — try multiple selectors
            article_urls = parsed_tree.xpath(
                "//a[contains(@class,'SummaryItemHedLink')]/@href"
                " | //a[contains(@class,'summary-item__hed-link')]/@href"
                " | //h2/a/@href | //h3/a/@href"
            )
            seen = set()
            for ur in article_urls:
                if not ur:
                    continue
                full = ur if ur.startswith("http") else "https://www.vogue.in" + ur
                parsed = urlparse(full)
                if "vogue.in" not in parsed.netloc:
                    continue
                parts = [p for p in parsed.path.strip("/").split("/") if p]
                if len(parts) < 2:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
