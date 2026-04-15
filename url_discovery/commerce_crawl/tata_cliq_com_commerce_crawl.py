from sdf_module.url_discovery import *
import logging
logger = logging.getLogger(__name__)
from urllib.parse import urljoin
import re

class TataCliqComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            dom = sdfFetch.get_page_content_hash(keyurl)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            next_links = parsed_tree.xpath("//a[@rel='next']/@href")
            if next_links:
                pagination_url.append(urljoin(keyurl, next_links[0]))
            else:
                m = re.search(r"([?&])page=(\d+)", keyurl)
                if m:
                    cur = int(m.group(2))
                    for p in range(cur + 1, cur + 11):
                        pagination_url.append(re.sub(r"([?&])page=\d+", rf"\1page={p}", keyurl, count=1))
                else:
                    connector = "&" if "?" in keyurl else "?"
                    for p in range(2, 12):
                        pagination_url.append(f"{keyurl}{connector}page={p}")
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page", "")
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            hrefs = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            rank = 1
            for href in hrefs:
                full = urljoin(url, href)
                # Tata CLiQ product URLs: /product-name/p-mp<id>
                # Also accept generic /p/ and /product/ patterns
                if "/p/" not in full and "/p-" not in full and "/product/" not in full:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(f"{full}|{{'rank': {rank}}}")
                rank += 1
        except Exception as e:
            logger.warning("Exception occurred: %s", e)
        return product_url
