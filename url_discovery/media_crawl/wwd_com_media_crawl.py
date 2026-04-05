from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse

# WWD is a WordPress site — pagination uses /page/N/ path format
class WwdComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            base = keyurl.rstrip("/")
            # page 1 is already the seed URL; start from page 2
            for i in range(2, 12):
                pagination_url.append(f"{base}/page/{i}/")
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
                if "wwd.com" not in parsed.netloc:
                    continue
                path = parsed.path.lower()
                # WWD article paths: /fashion-news/some-story-123456789/
                # Skip section indexes and utility pages
                skip_segments = {"page", "tag", "author", "category", "search", "feed", "wp-content"}
                parts = [p for p in path.strip("/").split("/") if p]
                if not parts:
                    continue
                if parts[0] in skip_segments:
                    continue
                # must have at least 2 path segments (section/slug) and end with digit (WWD article IDs)
                if len(parts) < 2:
                    continue
                if not parts[-1][-1].isdigit():
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
