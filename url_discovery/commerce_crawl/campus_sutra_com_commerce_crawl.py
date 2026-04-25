from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages, wordpress_pages
from urllib.parse import urljoin

class CampusSutraComCommerceCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            # Most commerce sites use ?page=N pagination.
            # Swap for wordpress_pages(keyurl) if the site uses /page/N/ instead.
            pagination_url = querystring_pages(keyurl, param="page", start=1, count=10)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            # TODO: update XPath to match product card links on this site
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            links = parsed_tree.xpath("//a[contains(@href,'/p/')]/@href | //a[contains(@href,'/product')]/@href")
            seen = set()
            for link in links:
                full = urljoin(url, link)
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
