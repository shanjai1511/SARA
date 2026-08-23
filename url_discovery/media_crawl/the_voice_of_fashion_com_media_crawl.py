from sdf_module.url_discovery import *
import re
import json as _json
import requests as _requests
import logging
logger = logging.getLogger(__name__)

# thevoiceoffashion.com was rebuilt on a new platform; the old WordPress-style
# /stories/, /runway/, /news/ sections (and /page/N/ pagination) are gone
# (all 404 now). The new site's /category/<slug>-<id> pages are a JS/AJAX
# shell: the article list is fetched client-side via a POST to a JSON API
# (see assets/websiteservices/category.js -> getCatData_v2/getMoreCatData_v2),
# so a plain GET of the category page (what sdfFetch does) returns an empty
# shell with no article links.
#
# Verified directly against the live API:
#   POST https://www.thevoiceoffashion.com/services/category/category
#        {"id": "<category id>", "subcat": ""}          -> first page of articles
#   POST https://www.thevoiceoffashion.com/services/category/categoryLoadmore
#        {"id": "<category id>", "pageno": <n>, "subcat": ""} -> subsequent pages
#
# The article URL only needs a correct trailing "-<id>" — the site resolves
# /any/path/here-<id> to the right article regardless of the slug text in
# between (confirmed: /x/y/z-6745 returns 200 for article id 6745) — so we
# rebuild a human-readable slug from the title for a clean URL, but only the
# id actually has to be right.
#
# Categories picked (verified live, most fashion-relevant of the current nav):
#   3 = Centrestage      (main fashion features/opinion/shows)
#   2 = Fabric of India  (textile heritage)
#   5 = Intersections    (fashion x art/culture)

BASE_URL     = "https://www.thevoiceoffashion.com/"
SERVICE_BASE = "https://www.thevoiceoffashion.com/services/category/"
_ID_RE       = re.compile(r"-(\d+)/?$")
_HEADERS     = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Content-Type": "application/json; charset=utf-8",
}


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text or "")
    text = re.sub(r"\s+", "-", text.strip())
    return text.lower() or "article"


def _post_json(endpoint: str, payload: dict, max_retries: int = 3, timeout: int = 30):
    url = SERVICE_BASE + endpoint
    for attempt in range(max_retries + 1):
        try:
            resp = _requests.post(url, data=_json.dumps(payload), headers=_HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning("Exception calling %s (attempt %s): %s", url, attempt + 1, e)
    return None


class TheVoiceOfFashionComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            m = _ID_RE.search(keyurl.split("?")[0])
            if not m:
                return pagination_url
            for i in range(2, 9):
                pagination_url.append(f"{keyurl}?page={i}")
        except Exception as e:
            logger.warning("Exception: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            base, _, qs = url.partition("?")
            m = _ID_RE.search(base)
            if not m:
                raise Exception(f"Could not find category id in {url}")
            category_id = m.group(1)
            page_match = re.search(r"page=(\d+)", qs)
            pageno = int(page_match.group(1)) if page_match else 1

            if pageno <= 1:
                data = _post_json("category", {"id": category_id, "subcat": ""})
                if not data:
                    raise Exception("No response from category API")
                category_name = data.get("categoryname", "")
                articles = data.get("articles", []) or []
            else:
                data = _post_json("categoryLoadmore", {"id": category_id, "pageno": pageno, "subcat": ""})
                if not data or data.get("status") not in (None, "success"):
                    raise Exception("No response from categoryLoadmore API")
                category_name = None  # each article carries its own categoryname
                articles = data.get("articles", []) or []

            seen = set()
            for art in articles:
                art_id = art.get("id")
                title = art.get("title", "")
                if not art_id:
                    continue
                cat = _slugify(art.get("categoryname") or category_name or "centrestage")
                subcat = _slugify(art.get("subcategoryname") or "features")
                slug = _slugify(title)
                full = f"{BASE_URL}{cat}/{subcat}/{slug}-{art_id}"
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
