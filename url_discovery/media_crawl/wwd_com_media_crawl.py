from sdf_module.url_discovery import *
from urllib.parse import urljoin

class WwdComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            connector = "&" if "?" in keyurl else "?"
            for i in range(1, 11):
                pagination_url.append(f"{keyurl}{connector}page={i}")
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page","")
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            links = parsed_tree.xpath("//a[@href]/@href")
            seen = set()
            for link in links:
                full = urljoin(url, link)
                if not any(k in full.lower() for k in ["/article", "/news", "/story", "/feature"]):
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
