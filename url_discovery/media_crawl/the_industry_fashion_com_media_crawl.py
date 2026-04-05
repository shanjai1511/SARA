from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse

# the-industry.fashion is WordPress — pagination is /page/N/
# Article URLs are bare slugs: the-industry.fashion/some-article-title/
# (no /news/ or /article/ prefix in the article slug itself)
_SKIP_PATHS = {
    "page", "tag", "author", "category", "wp-content", "wp-includes",
    "wp-json", "feed", "search", "about", "contact", "advertise",
    "subscribe", "privacy", "terms", "news", "analysis", "comment",
}


class TheIndustryFashionComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            base = keyurl.rstrip("/")
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
                if "the-industry.fashion" not in parsed.netloc:
                    continue
                parts = [p for p in parsed.path.strip("/").split("/") if p]
                # must have exactly one path segment (the article slug)
                if len(parts) != 1:
                    continue
                if parts[0].lower() in _SKIP_PATHS:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
