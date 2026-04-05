from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse

# Non-article paths to skip on thefashionlaw.com
_TFL_SKIP = {
    "category", "tag", "author", "page", "wp-content", "wp-includes",
    "wp-json", "feed", "search", "about", "contact", "subscribe",
    "advertise", "privacy", "terms", "cookie",
}


class TheFashionLawComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            # The Fashion Law category pages use ?page=N
            connector = "&" if "?" in keyurl else "?"
            for i in range(1, 11):
                pagination_url.append(f"{keyurl}{connector}page={i}")
        except Exception as e:
            print(f"Exception occurred: {e}")
        return pagination_url[:10]

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            url = url.replace("-page", "")
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No proper DOM found")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))

            # Strategy: article links are inside <article> elements on listing pages.
            # Fallback: any same-domain link whose first path segment is a slug
            # (not a nav/utility path).
            links = parsed_tree.xpath("//article//a[@href]/@href") or \
                    parsed_tree.xpath("//a[@href]/@href")

            seen = set()
            for link in links:
                full = urljoin(url, link)
                parsed = urlparse(full)
                # must be on thefashionlaw.com
                if "thefashionlaw.com" not in parsed.netloc:
                    continue
                path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                if not path_parts:
                    continue
                # skip navigation and utility paths
                if path_parts[0].lower() in _TFL_SKIP:
                    continue
                # article slugs are typically a single path segment (no nesting)
                if len(path_parts) > 2:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                product_url.append(full)
        except Exception as e:
            print(f"Exception occurred: {e}")
        return product_url[:10]
