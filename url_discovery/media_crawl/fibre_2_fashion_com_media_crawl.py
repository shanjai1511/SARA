from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse

# Fibre2Fashion uses numeric path-segment pagination:
#   /industry-article/fashion/  →  /industry-article/fashion/1/  /industry-article/fashion/2/  ...
class Fibre2FashionComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            base = keyurl.rstrip("/")
            # page 0 is the seed; pages 1-9 via numeric suffix
            for i in range(1, 11):
                pagination_url.append(f"{base}/{i}/")
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            links = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            for link in links:
                full = urljoin(url, link)
                parsed = urlparse(full)
                if "fibre2fashion.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                # F2F article paths: /industry-article/<slug>/ or /news/<slug>/
                if not any(seg in path for seg in ["/industry-article/", "/news/", "/article/"]):
                    continue
                # skip pure category listing pages (path ends with a number)
                parts = [p for p in path.strip("/").split("/") if p]
                if parts and parts[-1].isdigit():
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
