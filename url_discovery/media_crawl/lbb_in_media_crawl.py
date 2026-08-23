from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse
import re
import logging
logger = logging.getLogger(__name__)

DOMAIN = "lbb.in"
# lbb.in is a fully client-rendered Next.js app: the server HTML for
# /<city>/fashion/ contains a single <a href="/"> and pulls everything else
# from https://api.lbb.in/ at runtime, so there was never any XPath that
# could have found article links there -- the "//a[@href]" list is
# structurally empty regardless of selector. robots.txt still points at a
# real XML sitemap (https://lbb.in/sitemap/ -> discovery/{0..N}.xml) that
# lists every published article as https://lbb.in/<city>/<slug>/, so
# discovery walks that sitemap and keeps only fashion-related slugs instead
# of trying to scrape the SPA shell.
SITEMAP_SHARDS = 6
FASHION_KEYWORDS = [
    'fashion', 'style', 'wear', 'outfit', 'cloth', 'apparel', 'dress',
    'ethnic', 'saree', 'kurta', 'kurti', 'lehenga', 'boutique', 'designer',
    'footwear', 'bridal', 'couture', 'sneaker', 'jewellery', 'jewelry',
    'handbag', 'denim',
]


class LbbInMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += [f"https://lbb.in/sitemap/discovery/{i}.xml" for i in range(SITEMAP_SHARDS)]
        except Exception as e:
            logger.warning("Exception: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No DOM")
            body = dom.get("page_doc", "") or ""
            seen = set()
            if "<urlset" in body or "<loc>" in body:
                # Sitemap shard: pull <loc> entries directly, no DOM needed.
                for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", body):
                    p = urlparse(loc)
                    if DOMAIN not in p.netloc:
                        continue
                    if not any(kw in loc.lower() for kw in FASHION_KEYWORDS):
                        continue
                    if loc not in seen:
                        seen.add(loc)
                        product_url.append(loc)
            else:
                # Fallback for any lbb.in page that does return server-rendered
                # links (e.g. if the SPA shell changes again in the future).
                parsed_tree = html.fromstring(body)
                for href in parsed_tree.xpath("//a[@href]/@href"):
                    full = urljoin(url, href)
                    p    = urlparse(full)
                    if DOMAIN not in p.netloc:
                        continue
                    parts = [s for s in p.path.strip("/").split("/") if s]
                    if len(parts) < 2:
                        continue
                    if full not in seen:
                        seen.add(full)
                        product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
