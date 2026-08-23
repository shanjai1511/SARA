from sdf_module.url_discovery import *
from urllib.parse import urljoin, urlparse
import logging
logger = logging.getLogger(__name__)

# Vox's "The Goods" (consumer/fashion vertical) was shut down in 2020 and its
# "Recode" tech vertical was folded into /technology in 2021 — both old seeds
# (/the-goods/fashion, /recode) now 404 or redirect away. Vox no longer has a
# fashion-specific section; the closest currently-live equivalent coverage is
# its /culture and /life sections (occasional style/fashion-adjacent pieces,
# e.g. "wardrobe-digital-closet-catalog-app"). Vox runs on the same Vox Media
# platform as The Verge, so it uses the same /<section>/archives/<page>
# pagination (not ?page=N or /page/N/) and the same
# /<section>/<numeric-id>/<slug> article URL shape.
DOMAIN = "vox.com"
SKIP_SEGMENTS = ['page', 'archives', 'tag', 'author', 'category', 'search', 'feed', 'topic', 'video', 'gallery', 'photo', 'quiz', 'newsletter']


class VoxComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            base = keyurl.rstrip("/")
            for i in range(2, 10):
                pagination_url.append(f"{base}/archives/{i}")
        except Exception as e:
            logger.warning("Exception: %s", e)
        return pagination_url

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        try:
            dom = sdfFetch.get_page_content_hash(url)
            if dom.get("status_code") != 200:
                raise Exception("No DOM")
            parsed_tree = html.fromstring(dom.get("page_doc", ""))
            seen = set()
            for href in parsed_tree.xpath("//a[@href]/@href"):
                full = urljoin(url, href)
                p    = urlparse(full)
                if DOMAIN not in p.netloc:
                    continue
                parts = [s for s in p.path.strip("/").split("/") if s]
                # Vox article URLs are /<section>/<numeric-id>/<slug>
                if len(parts) < 3 or parts[0] in SKIP_SEGMENTS or not parts[1].isdigit():
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
