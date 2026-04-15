from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin, urlparse

class AmazonInCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            dom = sdfFetch.get_page_content_hash(keyurl, proxy="webshare_proxy")
            if dom["status_code"] != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom["page_doc"])
            # Try to find max page number from pagination
            pages = parsed_tree.xpath(
                "//span[contains(@class,'a-pagination')]//li/a/text()"
                " | //ul[contains(@class,'a-pagination')]//li[@class='a-normal']/a/text()"
            )
            nums = [int(p) for p in pages if p.strip().isdigit()]
            if nums:
                max_page = min(max(nums), 10)  # cap at 10 pages
                for page in range(2, max_page + 1):
                    pagination_url.append(f"{keyurl}&page={page}")
            else:
                # fallback: generate pages 2-10
                for page in range(2, 11):
                    pagination_url.append(f"{keyurl}&page={page}")
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

            # Use multiple XPaths for Amazon's frequently changing class names
            hrefs = (
                parsed_tree.xpath("//div[@data-component-type='s-search-result']//h2/a/@href")
                or parsed_tree.xpath("//div[@data-component-type='s-search-result']//a[contains(@class,'a-link-normal')]/@href")
                or parsed_tree.xpath("//div[@data-asin and string-length(@data-asin)>0]//h2/a/@href")
            )

            seen = set()
            rank = 1
            for href in hrefs:
                if not href:
                    continue
                full = "https://www.amazon.in" + href if href.startswith("/") else href
                parsed = urlparse(full)
                if "amazon.in" not in parsed.netloc:
                    continue
                # Amazon product URLs contain /dp/ or /gp/product/
                if "/dp/" not in full and "/gp/product/" not in full:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
                rank += 1
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
