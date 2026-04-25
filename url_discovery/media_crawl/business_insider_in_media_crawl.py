from sdf_module.url_discovery import *
from core.discovery_helpers import wordpress_pages, querystring_pages
from urllib.parse import urljoin

class BusinessInsiderInMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            # Most media sites use WordPress /page/N/ pagination.
            # Swap for querystring_pages(keyurl) if the site uses ?page=N instead.
            pagination_url = wordpress_pages(keyurl, count=10)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            # TODO: set correct domain and article path prefixes
            DOMAIN = "example.com"
            ARTICLE_PATHS = ["/news/", "/article/", "/features/"]
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            seen = set()
            for link in parsed_tree.xpath("//a[@href]/@href"):
                full = urljoin(url, link)
                if DOMAIN not in full:
                    continue
                if not any(p in full for p in ARTICLE_PATHS):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
