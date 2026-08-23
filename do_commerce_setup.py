"""
Run: python do_commerce_setup.py
Writes/overwrites all discovery YAML and Python files for commerce sites.

Existing PSS sites: only their YAMLs are updated (Python kept as-is).
New sites: both YAML and Python are written.
"""
import os
from pathlib import Path

BASE = Path(__file__).parent
DISCOVERY_DIR = BASE / "url_discovery" / "commerce_crawl"

# Sites whose Python files must NOT be overwritten (custom/complex code)
PROTECTED_PY = {
    "amazon_in",
    "myntra_com",
    "flipkart_com",
    "meesho_com",
    "ajio_com",
    "tata_cliq_com",
    "max_com",
    "limeroad_com",
    "shoppersstop_com",
    "styleunion_com",
    "nykaa_fashion_com",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _class_name(site_name: str) -> str:
    """snitch_com -> SnitchComCommerceCrawl"""
    return "".join(w.capitalize() for w in f"{site_name}_commerce_crawl".split("_"))


def write_yaml(site_name: str, seed_urls: list, use_proxy: bool = True) -> Path:
    """Write a 3-depth discovery YAML for the given site."""
    lines = ["depth0:"]
    lines.append("  seed_url: [")
    for i, url in enumerate(seed_urls):
        comma = "," if i < len(seed_urls) - 1 else ""
        lines.append(f'    "{url}"{comma}')
    lines.append("  ]")
    lines.append("depth1:")
    lines.append("  method_name: get_pagination_url")
    lines.append("depth2:")
    lines.append("  method_name: get_product_url")
    lines.append("request_params:")
    if use_proxy:
        lines.append("  proxy: webshare_proxy")
    lines.append("  timeout: 30")
    lines.append("  max_retries: 3")
    lines.append("")

    out = DISCOVERY_DIR / f"{site_name}_commerce_crawl.yml"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_py_standard(
    site_name: str,
    domain: str,
    product_patterns: list,
    pagination_param: str = "page",
    pagination_start: int = 1,
    pagination_count: int = 20,
) -> Path:
    """Write standard querystring discovery Python."""
    cls = _class_name(site_name)
    patterns_repr = repr(product_patterns)
    xpath_parts = " | ".join(
        f'//a[contains(@href,"{p}")]/@href' for p in product_patterns
    )

    code = f'''from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin
import logging
logger = logging.getLogger(__name__)

DOMAIN = "https://{domain}"
PRODUCT_PATTERNS = {patterns_repr}


class {cls}():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            pagination_url = querystring_pages(
                keyurl, param="{pagination_param}", start={pagination_start}, count={pagination_count}
            )
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
                if DOMAIN not in full:
                    continue
                if not any(p in full for p in PRODUCT_PATTERNS):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
'''
    out = DISCOVERY_DIR / f"{site_name}_commerce_crawl.py"
    out.write_text(code, encoding="utf-8")
    return out


def write_py_shopify(site_name: str, domain: str, pagination_count: int = 20) -> Path:
    """Write Shopify discovery Python."""
    cls = _class_name(site_name)

    code = f'''from sdf_module.url_discovery import *
from core.discovery_helpers import shopify_pages
from urllib.parse import urljoin
import logging
logger = logging.getLogger(__name__)

DOMAIN = "https://{domain}"


class {cls}():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = []
        try:
            pagination_url = shopify_pages(keyurl, count={pagination_count})
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
            for href in parsed_tree.xpath("//a[contains(@href,'/products/')]/@href"):
                full = urljoin(url, href)
                if DOMAIN not in full:
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
'''
    out = DISCOVERY_DIR / f"{site_name}_commerce_crawl.py"
    out.write_text(code, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Site definitions
# ---------------------------------------------------------------------------

def _shopify_seeds(domain: str, paths: list) -> list:
    """Build full Shopify seed URLs from a domain + collection paths."""
    return [f"https://{domain}{p}" for p in paths]


# (site_name, seed_urls)
EXISTING_PSS_YAMLS = [
    (
        "myntra_com",
        [
            "https://www.myntra.com/tshirts",
            "https://www.myntra.com/women-tshirts",
            "https://www.myntra.com/polo-tshirts",
            "https://www.myntra.com/kurtas",
            "https://www.myntra.com/women-jeans",
            "https://www.myntra.com/men-jeans",
            "https://www.myntra.com/dresses",
            "https://www.myntra.com/men-shirts",
            "https://www.myntra.com/sarees",
            "https://www.myntra.com/women-tops",
            "https://www.myntra.com/men-ethnic",
            "https://www.myntra.com/sweatshirts",
            "https://www.myntra.com/activewear-women",
            "https://www.myntra.com/activewear-men",
        ],
    ),
    (
        "amazon_in",
        [
            "https://www.amazon.in/s?k=men+t+shirts&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=women+t+shirts&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=men+polo+shirts&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=women+kurtas&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=men+shirts&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=men+jeans&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=women+jeans&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=women+dresses&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=men+trousers&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=women+ethnic+wear&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=men+activewear&rh=n%3A1968024031",
            "https://www.amazon.in/s?k=women+activewear&rh=n%3A1968024031",
        ],
    ),
    (
        "flipkart_com",
        [
            "https://www.flipkart.com/mens-clothing/tshirts/pr?sid=clo,ash,ank",
            "https://www.flipkart.com/womens-clothing/tshirts-and-tops/pr?sid=clo,apn,axe,aj7",
            "https://www.flipkart.com/mens-clothing/jeans/pr?sid=clo,ash,aji",
            "https://www.flipkart.com/womens-clothing/jeans/pr?sid=clo,apn,axe,ahw",
            "https://www.flipkart.com/mens-clothing/shirts/pr?sid=clo,ash,anl",
            "https://www.flipkart.com/womens-clothing/kurtas-kurtis/pr?sid=clo,apn,axe,ank",
            "https://www.flipkart.com/womens-clothing/dresses/pr?sid=clo,apn,axe,acr",
            "https://www.flipkart.com/mens-clothing/casual-shoes/pr?sid=clo,ash,ajm",
            "https://www.flipkart.com/womens-clothing/ethnic-wear/sarees/pr?sid=clo,apn,axe,ajy",
            "https://www.flipkart.com/mens-clothing/sweatshirts/pr?sid=clo,ash,ank,aho",
        ],
    ),
    (
        "meesho_com",
        [
            "https://www.meesho.com/men-t-shirts/pl/3lq",
            "https://www.meesho.com/women-t-shirts/pl/3es",
            "https://www.meesho.com/polo-t-shirts/pl/3lr",
            "https://www.meesho.com/women-kurtas/pl/3ew",
            "https://www.meesho.com/women-dresses/pl/3et",
            "https://www.meesho.com/men-shirts/pl/3lp",
            "https://www.meesho.com/women-jeans/pl/3ev",
            "https://www.meesho.com/men-jeans/pl/3ls",
            "https://www.meesho.com/women-tops/pl/3eu",
            "https://www.meesho.com/sarees/pl/3ey",
            "https://www.meesho.com/men-ethnic-wear/pl/3lv",
        ],
    ),
    (
        "ajio_com",
        [
            "https://www.ajio.com/men-tshirts-polos/c/830301001",
            "https://www.ajio.com/men-shirts/c/830301003",
            "https://www.ajio.com/men-jeans/c/830301004",
            "https://www.ajio.com/men-trousers-chinos/c/830301005",
            "https://www.ajio.com/men-shorts/c/830301009",
            "https://www.ajio.com/men-jackets-coats/c/830301011",
            "https://www.ajio.com/men-sweatshirts-hoodies/c/830301010",
            "https://www.ajio.com/women-tshirts-tops/c/830303006",
            "https://www.ajio.com/women-kurtas-kurtis/c/830303013",
            "https://www.ajio.com/women-dresses/c/830303007",
            "https://www.ajio.com/women-jeans/c/830303004",
            "https://www.ajio.com/women-trousers-capris/c/830303005",
            "https://www.ajio.com/women-sarees/c/830303017",
            "https://www.ajio.com/women-bags/c/830316",
            "https://www.ajio.com/kids-tshirts/c/830202001",
            "https://www.ajio.com/kids-dresses/c/830202004",
            "https://www.ajio.com/kids-shoes/c/830209",
        ],
    ),
    (
        "tata_cliq_com",
        [
            "https://www.tatacliq.com/t-shirts-for-men/c-msh11106/",
            "https://www.tatacliq.com/t-shirts-for-women/c-msh12106/",
            "https://www.tatacliq.com/shirts-for-men/c-msh11107/",
            "https://www.tatacliq.com/jeans-for-men/c-msh11109/",
            "https://www.tatacliq.com/jeans-for-women/c-msh12109/",
            "https://www.tatacliq.com/kurtas-for-women/c-msh12110/",
            "https://www.tatacliq.com/dresses-for-women/c-msh12105/",
            "https://www.tatacliq.com/trousers-for-men/c-msh11110/",
            "https://www.tatacliq.com/tops-for-women/c-msh12107/",
            "https://www.tatacliq.com/sweatshirts-for-men/c-msh11116/",
        ],
    ),
    (
        "nykaa_fashion_com",
        [
            "https://www.nykaafashion.com/women-tops-t-shirts/c/7",
            "https://www.nykaafashion.com/men-tshirts/c/9",
            "https://www.nykaafashion.com/women-kurtas/c/8",
            "https://www.nykaafashion.com/women-dresses/c/10",
            "https://www.nykaafashion.com/women-jeans/c/12",
            "https://www.nykaafashion.com/men-shirts/c/11",
            "https://www.nykaafashion.com/women-co-ords/c/14",
            "https://www.nykaafashion.com/women-ethnic-wear/c/13",
        ],
    ),
    (
        "max_com",
        [
            "https://www.maxfashion.in/in/en/Men-Clothes/T-Shirts-Polo-Shirts/c/MenTShirts",
            "https://www.maxfashion.in/in/en/Women/T-Shirts/c/WomenTShirts",
            "https://www.maxfashion.in/in/en/Kids/Boys/T-Shirts/c/KidsBoysTShirts",
            "https://www.maxfashion.in/in/en/Men-Clothes/Shirts/c/MenShirts",
            "https://www.maxfashion.in/in/en/Men-Clothes/Jeans/c/MenJeans",
            "https://www.maxfashion.in/in/en/Women/Jeans/c/WomenJeans",
            "https://www.maxfashion.in/in/en/Women/Kurtas-Kurtis/c/WomenKurtas",
            "https://www.maxfashion.in/in/en/Women/Dresses/c/WomenDresses",
            "https://www.maxfashion.in/in/en/Men-Clothes/Trousers/c/MenTrousers",
            "https://www.maxfashion.in/in/en/Women/Tops/c/WomenTops",
            "https://www.maxfashion.in/in/en/Kids/Girls/Dresses/c/KidsGirlsDresses",
        ],
    ),
    (
        "limeroad_com",
        [
            "https://www.limeroad.com/men-t-shirts",
            "https://www.limeroad.com/t-shirts-for-women",
            "https://www.limeroad.com/women-kurtas",
            "https://www.limeroad.com/women-dresses",
            "https://www.limeroad.com/women-jeans",
            "https://www.limeroad.com/men-shirts",
            "https://www.limeroad.com/men-jeans",
            "https://www.limeroad.com/women-tops",
            "https://www.limeroad.com/women-ethnic-wear",
            "https://www.limeroad.com/men-ethnic-wear",
        ],
    ),
    (
        "shoppersstop_com",
        [
            "https://www.shoppersstop.com/women-westernwear-dresses/c-1506",
            "https://www.shoppersstop.com/women-westernwear-tops/c-1502",
            "https://www.shoppersstop.com/men-shirts/c-1301",
            "https://www.shoppersstop.com/men-tshirts/c-1302",
            "https://www.shoppersstop.com/women-westernwear-jeans/c-1503",
            "https://www.shoppersstop.com/men-jeans/c-1303",
            "https://www.shoppersstop.com/women-ethnic-kurtas/c-1401",
            "https://www.shoppersstop.com/men-ethnic/c-1304",
            "https://www.shoppersstop.com/women-westernwear-trousers/c-1504",
            "https://www.shoppersstop.com/men-trousers/c-1305",
        ],
    ),
    (
        "styleunion_com",
        [
            "https://styleunion.in/collections/mens-t-shirts",
            "https://styleunion.in/collections/womens-t-shirts",
            "https://styleunion.in/collections/mens-shirts",
            "https://styleunion.in/collections/womens-tops",
            "https://styleunion.in/collections/mens-polo",
            "https://styleunion.in/collections/womens-dresses",
            "https://styleunion.in/collections/mens-jeans",
            "https://styleunion.in/collections/womens-jeans",
            "https://styleunion.in/collections/mens-sweatshirts",
            "https://styleunion.in/collections/womens-sweatshirts",
            "https://styleunion.in/collections/mens-shorts",
            "https://styleunion.in/collections/womens-kurtas",
        ],
    ),
]

# (site_name, domain, collection_paths)
SHOPIFY_SITES = [
    (
        "snitch_com",
        "snitch.co.in",
        [
            "/collections/t-shirts",
            "/collections/oversized-t-shirts",
            "/collections/polo-t-shirts",
            "/collections/shirts",
            "/collections/jeans",
            "/collections/shorts",
            "/collections/joggers",
        ],
    ),
    (
        "the_souled_store_com",
        "thesouledstore.com",
        [
            "/men/t-shirts",
            "/women/t-shirts",
            "/men/shirts",
            "/men/hoodies",
            "/women/tops",
        ],
    ),
    (
        "bonkers_corner_com",
        "bonkerscorner.com",
        [
            "/collections/t-shirts",
            "/collections/oversized",
            "/collections/all",
        ],
    ),
    (
        "hrx_com",
        "hrxbrand.com",
        [
            "/collections/men-t-shirts",
            "/collections/women-t-shirts",
            "/collections/men-shorts",
            "/collections/women-activewear",
        ],
    ),
    (
        "the_bear_house_com",
        "thebearhouse.in",
        [
            "/collections/t-shirts",
            "/collections/shirts",
            "/collections/all",
        ],
    ),
    (
        "fablestreet_com",
        "fablestreet.com",
        [
            "/collections/tops",
            "/collections/dresses",
            "/collections/shirts",
            "/collections/blazers",
        ],
    ),
    (
        "suta_in",
        "suta.in",
        [
            "/collections/sarees",
            "/collections/blouses",
            "/collections/kurta",
        ],
    ),
    (
        "no_nasties_in",
        "nonasties.in",
        [
            "/collections/men-organic-t-shirts",
            "/collections/women-organic-t-shirts",
            "/collections/kids",
        ],
    ),
    (
        "doodlage_in",
        "doodlage.in",
        [
            "/collections/all",
            "/collections/women",
            "/collections/men",
        ],
    ),
    (
        "boheco_com",
        "boheco.com",
        [
            "/collections/women",
            "/collections/men",
            "/collections/accessories",
        ],
    ),
    (
        "the_label_life_com",
        "thelabellife.com",
        [
            "/collections/clothing",
            "/collections/all",
        ],
    ),
    (
        "freecultr_com",
        "freecultr.com",
        [
            "/collections/men-t-shirts",
            "/collections/women-tops",
            "/collections/hoodies",
            "/collections/joggers",
        ],
    ),
    (
        "xyxx_com",
        "xyxxcrew.com",
        [
            "/collections/all",
            "/collections/t-shirts",
            "/collections/lounge",
            "/collections/innerwear",
        ],
    ),
    (
        "damensch_com",
        "damensch.com",
        [
            "/collections/t-shirts",
            "/collections/polos",
            "/collections/innerwear",
            "/collections/joggers",
            "/collections/activewear",
        ],
    ),
    (
        "nalli_com",
        "nalli.com",
        [
            "/collections/sarees",
            "/collections/salwar-suits",
            "/collections/lehengas",
        ],
    ),
    (
        "w_for_woman_com",
        "wforwoman.com",
        [
            "/collections/kurtas",
            "/collections/dresses",
            "/collections/tops",
            "/collections/co-ords",
        ],
    ),
    (
        "global_desi_in",
        "globaldesi.in",
        [
            "/collections/kurtas",
            "/collections/dresses",
            "/collections/tops",
            "/collections/tunics",
        ],
    ),
    (
        "house_of_masaba_com",
        "houseofmasaba.com",
        [
            "/collections/kurtas",
            "/collections/sarees",
            "/collections/t-shirts",
            "/collections/dresses",
        ],
    ),
    (
        "house_of_indya_com",
        "houseofindya.com",
        [
            "/collections/kurtas",
            "/collections/tops",
            "/collections/dresses",
            "/collections/co-ords",
        ],
    ),
    (
        "libas_in",
        "libas.in",
        [
            "/collections/kurtas",
            "/collections/dresses",
            "/collections/tops",
            "/collections/sarees",
            "/collections/tshirts",
        ],
    ),
    (
        "andalso_in",
        "andalso.in",
        [
            "/collections/dresses",
            "/collections/tops",
            "/collections/co-ords",
            "/collections/kurtas",
        ],
    ),
    (
        "nicobar_com",
        "nicobar.com",
        [
            "/collections/women-clothing",
            "/collections/men-clothing",
            "/collections/women-dresses",
            "/collections/men-tops",
        ],
    ),
    (
        "westside_com",
        "westside.com",
        [
            "/collections/men-tshirts",
            "/collections/women-tops",
            "/collections/men-shirts",
            "/collections/women-dresses",
            "/collections/men-jeans",
        ],
    ),
    (
        "frontier_raas_com",
        "frontierraas.com",
        [
            "/collections/lehengas",
            "/collections/sarees",
            "/collections/salwar-suits",
        ],
    ),
    (
        "dressindia_in",
        "dressindia.in",
        [
            "/collections/all",
            "/collections/kurtas",
            "/collections/sarees",
        ],
    ),
    (
        "byshree_com",
        "byshree.com",
        [
            "/collections/kurtas",
            "/collections/sarees",
            "/collections/tops",
        ],
    ),
    (
        "sabyasachi_com",
        "sabyasachi.com",
        [
            "/collections/ready-to-wear",
            "/collections/sarees",
            "/collections/lehengas",
        ],
    ),
    (
        "okhai_org",
        "okhai.org",
        [
            "/collections/all",
            "/collections/women",
            "/collections/men",
        ],
    ),
    (
        "pretty_secrets_com",
        "prettysecrets.com",
        [
            "/collections/bra",
            "/collections/panties",
            "/collections/lingerie-sets",
            "/collections/nightwear",
        ],
    ),
    (
        "da_milano_com",
        "damilano.com",
        [
            "/collections/bags",
            "/collections/shoes",
            "/collections/accessories",
            "/collections/wallets",
        ],
    ),
]

# (site_name, domain, seed_urls, product_patterns, pagination_param, pagination_start, pagination_count)
STANDARD_SITES = [
    (
        "hm_com",
        "www2.hm.com",
        [
            "https://www2.hm.com/en_in/men/shop-by-product/t-shirts-tanks.html",
            "https://www2.hm.com/en_in/ladies/tops.html",
            "https://www2.hm.com/en_in/men/shop-by-product/shirts.html",
            "https://www2.hm.com/en_in/ladies/dresses.html",
            "https://www2.hm.com/en_in/men/shop-by-product/jeans.html",
            "https://www2.hm.com/en_in/ladies/jeans.html",
            "https://www2.hm.com/en_in/men/shop-by-product/hoodies-sweatshirts.html",
        ],
        ["/productpage.", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "marks_spencer_in",
        "marksandspencer.in",
        [
            "https://www.marksandspencer.in/men/t-shirts-polos",
            "https://www.marksandspencer.in/women/tops-t-shirts",
            "https://www.marksandspencer.in/men/shirts",
            "https://www.marksandspencer.in/men/jeans",
            "https://www.marksandspencer.in/women/jeans",
            "https://www.marksandspencer.in/women/dresses",
            "https://www.marksandspencer.in/women/kurtas-suits",
        ],
        ["/p/"],
        "page",
        1,
        20,
    ),
    (
        "zara_com",
        "www.zara.com",
        [
            "https://www.zara.com/in/en/man-tshirts-l838.html",
            "https://www.zara.com/in/en/woman-tshirts-l1362.html",
            "https://www.zara.com/in/en/man-shirts-l717.html",
            "https://www.zara.com/in/en/woman-dresses-l1066.html",
            "https://www.zara.com/in/en/man-jeans-l853.html",
            "https://www.zara.com/in/en/woman-jeans-l1119.html",
        ],
        ["/product/"],
        "page",
        1,
        20,
    ),
    (
        "bewakoof_com",
        "www.bewakoof.com",
        [
            "https://www.bewakoof.com/men-t-shirts",
            "https://www.bewakoof.com/women-t-shirts",
            "https://www.bewakoof.com/men-shirts",
            "https://www.bewakoof.com/women-tops",
            "https://www.bewakoof.com/men-joggers",
            "https://www.bewakoof.com/women-joggers",
            "https://www.bewakoof.com/men-shorts",
            "https://www.bewakoof.com/hoodie-sweatshirts",
            "https://www.bewakoof.com/men-polo-shirts",
        ],
        ["/products/", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "beyoung_in",
        "www.beyoung.in",
        [
            "https://www.beyoung.in/t-shirts",
            "https://www.beyoung.in/polo-t-shirts",
            "https://www.beyoung.in/men-shirts",
            "https://www.beyoung.in/women-tops",
            "https://www.beyoung.in/men-hoodies-sweatshirts",
            "https://www.beyoung.in/women-dresses",
            "https://www.beyoung.in/men-jeans",
        ],
        ["/product/", "/buy/"],
        "page",
        1,
        20,
    ),
    (
        "campus_sutra_com",
        "www.campussutra.com",
        [
            "https://www.campussutra.com/Men-T-Shirts",
            "https://www.campussutra.com/Women-T-Shirts",
            "https://www.campussutra.com/Men-Shirts",
            "https://www.campussutra.com/Men-Hoodies-Sweatshirts",
            "https://www.campussutra.com/Women-Hoodies-Sweatshirts",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "koovs_com",
        "www.koovs.com",
        [
            "https://www.koovs.com/men/t-shirts",
            "https://www.koovs.com/women/t-shirts",
            "https://www.koovs.com/men/tops",
            "https://www.koovs.com/women/tops",
            "https://www.koovs.com/men/shirts",
        ],
        ["/catalog/", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "urbanic_com",
        "www.urbanic.com",
        [
            "https://www.urbanic.com/women/tops",
            "https://www.urbanic.com/women/t-shirts",
            "https://www.urbanic.com/women/dresses",
            "https://www.urbanic.com/women/co-ords",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "lifestyle_stores_com",
        "www.lifestylestores.com",
        [
            "https://www.lifestylestores.com/in/en/MEN/APPAREL/T-SHIRTS-AND-POLOS/c/LF-EN-T-SHIRTS",
            "https://www.lifestylestores.com/in/en/WOMEN/APPAREL/TOPS/c/LF-EN-W-TOPS",
            "https://www.lifestylestores.com/in/en/MEN/APPAREL/SHIRTS/c/LF-EN-SHIRTS",
            "https://www.lifestylestores.com/in/en/WOMEN/APPAREL/DRESSES/c/LF-EN-W-DRESSES",
            "https://www.lifestylestores.com/in/en/MEN/APPAREL/JEANS/c/LF-EN-MEN-JEANS",
        ],
        ["/p/", "/product/"],
        "p",
        1,
        20,
    ),
    (
        "centralandme_com",
        "www.centralandme.com",
        [
            "https://www.centralandme.com/men/topwear/tshirts",
            "https://www.centralandme.com/women/topwear/tops",
            "https://www.centralandme.com/men/topwear/shirts",
            "https://www.centralandme.com/women/bottomwear/jeans",
            "https://www.centralandme.com/men/bottomwear/jeans",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "pantaloons_com",
        "www.pantaloons.com",
        [
            "https://www.pantaloons.com/c/men-tshirt",
            "https://www.pantaloons.com/c/women-tops",
            "https://www.pantaloons.com/c/men-shirts",
            "https://www.pantaloons.com/c/women-kurta",
            "https://www.pantaloons.com/c/men-jeans",
            "https://www.pantaloons.com/c/women-jeans",
            "https://www.pantaloons.com/c/men-trousers",
            "https://www.pantaloons.com/c/women-dresses",
        ],
        ["/p/", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "brand_factory_com",
        "www.brandfactoryonline.com",
        [
            "https://www.brandfactoryonline.com/men/t-shirts",
            "https://www.brandfactoryonline.com/women/tops",
            "https://www.brandfactoryonline.com/men/shirts",
            "https://www.brandfactoryonline.com/women/kurtas",
            "https://www.brandfactoryonline.com/men/jeans",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "vmart_com",
        "www.vmartretail.com",
        [
            "https://www.vmartretail.com/c/men-t-shirts",
            "https://www.vmartretail.com/c/women-tops",
            "https://www.vmartretail.com/c/men-shirts",
            "https://www.vmartretail.com/c/women-kurtas",
            "https://www.vmartretail.com/c/men-jeans",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "zudio_com",
        "www.zudio.com",
        [
            "https://www.zudio.com/c/men-tshirts",
            "https://www.zudio.com/c/women-tops",
            "https://www.zudio.com/c/men-shirts",
            "https://www.zudio.com/c/women-dresses",
            "https://www.zudio.com/c/men-jeans",
            "https://www.zudio.com/c/women-kurtas",
        ],
        ["/p/", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "reliance_trends_com",
        "www.reliancetrends.com",
        [
            "https://www.reliancetrends.com/men/tshirts",
            "https://www.reliancetrends.com/women/tops",
            "https://www.reliancetrends.com/men/shirts",
            "https://www.reliancetrends.com/women/kurtas",
            "https://www.reliancetrends.com/women/dresses",
        ],
        ["/p/", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "biba_in",
        "www.biba.in",
        [
            "https://www.biba.in/tops-and-tshirts.html",
            "https://www.biba.in/kurtas-for-women.html",
            "https://www.biba.in/salwar-kameez.html",
            "https://www.biba.in/dresses.html",
            "https://www.biba.in/skirts.html",
            "https://www.biba.in/coordinates.html",
        ],
        ["/p/", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "manyavar_com",
        "www.manyavar.com",
        [
            "https://www.manyavar.com/shop/kurta-set/",
            "https://www.manyavar.com/shop/sherwani/",
            "https://www.manyavar.com/shop/kurta/",
            "https://www.manyavar.com/shop/indo-western/",
            "https://www.manyavar.com/shop/bandhgala/",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "fabindia_com",
        "www.fabindia.com",
        [
            "https://www.fabindia.com/men/kurtas",
            "https://www.fabindia.com/women/kurtas-sets",
            "https://www.fabindia.com/men/tops-and-tshirts",
            "https://www.fabindia.com/women/tops-and-tshirts",
            "https://www.fabindia.com/women/sarees",
            "https://www.fabindia.com/men/shirts",
            "https://www.fabindia.com/women/dresses",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "soch_com",
        "www.soch.com",
        [
            "https://www.soch.com/collections/kurtas",
            "https://www.soch.com/collections/sarees",
            "https://www.soch.com/collections/tops",
            "https://www.soch.com/collections/dresses",
        ],
        ["/products/"],
        "page",
        1,
        20,
    ),
    (
        "craftsvilla_com",
        "www.craftsvilla.com",
        [
            "https://www.craftsvilla.com/sarees",
            "https://www.craftsvilla.com/kurtas",
            "https://www.craftsvilla.com/dresses",
            "https://www.craftsvilla.com/lehengas",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "voonik_com",
        "www.voonik.com",
        [
            "https://www.voonik.com/women/sarees",
            "https://www.voonik.com/women/kurtas",
            "https://www.voonik.com/women/tops",
            "https://www.voonik.com/women/dresses",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "aza_fashions_com",
        "www.azafashions.com",
        [
            "https://www.azafashions.com/category/women/indian-wear",
            "https://www.azafashions.com/category/women/western-wear",
            "https://www.azafashions.com/category/men/indian-wear",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "pernia_popup_shop_com",
        "www.perniaspopupshop.com",
        [
            "https://www.perniaspopupshop.com/women/kurtas",
            "https://www.perniaspopupshop.com/women/sarees",
            "https://www.perniaspopupshop.com/women/lehengas",
            "https://www.perniaspopupshop.com/women/dresses",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "ogaan_com",
        "www.ogaan.com",
        [
            "https://www.ogaan.com/shop/",
            "https://www.ogaan.com/shop/women/",
            "https://www.ogaan.com/shop/men/",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "luxepolis_com",
        "www.luxepolis.com",
        [
            "https://www.luxepolis.com/women/clothing",
            "https://www.luxepolis.com/men/clothing",
            "https://www.luxepolis.com/women/bags",
            "https://www.luxepolis.com/women/shoes",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "ritu_kumar_com",
        "www.ritukumar.com",
        [
            "https://www.ritukumar.com/women/sarees",
            "https://www.ritukumar.com/women/kurtas",
            "https://www.ritukumar.com/women/salwar-kameez",
            "https://www.ritukumar.com/women/lehengas",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "jaypore_com",
        "www.jaypore.com",
        [
            "https://www.jaypore.com/c/women-indian-wear",
            "https://www.jaypore.com/c/women-western-wear",
            "https://www.jaypore.com/c/men-clothing",
            "https://www.jaypore.com/c/women-sarees",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "kalki_fashion_com",
        "www.kalkifashion.com",
        [
            "https://www.kalkifashion.com/lehengas.html",
            "https://www.kalkifashion.com/sarees.html",
            "https://www.kalkifashion.com/salwar-kameez.html",
            "https://www.kalkifashion.com/gowns.html",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "chhabra555_com",
        "www.chhabra555.com",
        [
            "https://www.chhabra555.com/sarees.html",
            "https://www.chhabra555.com/suits.html",
            "https://www.chhabra555.com/lehengas.html",
            "https://www.chhabra555.com/kurtis.html",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "the_chennai_silks_com",
        "www.thechennaisilks.com",
        [
            "https://www.thechennaisilks.com/sarees",
            "https://www.thechennaisilks.com/dress-materials",
            "https://www.thechennaisilks.com/lehengas",
            "https://www.thechennaisilks.com/kurtis",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "pothys_com",
        "www.pothys.com",
        [
            "https://www.pothys.com/sarees.html",
            "https://www.pothys.com/salwars.html",
            "https://www.pothys.com/lehengas.html",
            "https://www.pothys.com/kurtis.html",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "rmkv_silks_com",
        "www.rmkvsilks.com",
        [
            "https://www.rmkvsilks.com/sarees",
            "https://www.rmkvsilks.com/salwars",
            "https://www.rmkvsilks.com/lehengas",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "nike_com",
        "www.nike.com",
        [
            "https://www.nike.com/in/w/mens-t-shirts-3rbdj",
            "https://www.nike.com/in/w/womens-t-shirts-2j488",
            "https://www.nike.com/in/w/mens-tops-shirts-6ahsc",
            "https://www.nike.com/in/w/womens-tops-shirts-57zfg",
            "https://www.nike.com/in/w/mens-shorts-38fph",
            "https://www.nike.com/in/w/mens-hoodies-pullovers-6rivl",
        ],
        ["/t/", "/product/"],
        "skip",
        0,
        20,
    ),
    (
        "adidas_in",
        "www.adidas.co.in",
        [
            "https://www.adidas.co.in/men-t-shirts",
            "https://www.adidas.co.in/women-t-shirts",
            "https://www.adidas.co.in/men-polo-shirts",
            "https://www.adidas.co.in/men-shorts",
            "https://www.adidas.co.in/women-shorts",
            "https://www.adidas.co.in/men-hoodies-and-sweatshirts",
            "https://www.adidas.co.in/men-tracksuits",
        ],
        ["/product/", "/p/"],
        "start",
        0,
        20,
    ),
    (
        "puma_com",
        "in.puma.com",
        [
            "https://in.puma.com/in/en/men/clothing/shirts-tees",
            "https://in.puma.com/in/en/women/clothing/shirts-tees",
            "https://in.puma.com/in/en/men/clothing/hoodies-and-sweatshirts",
            "https://in.puma.com/in/en/men/clothing/shorts",
            "https://in.puma.com/in/en/women/clothing/shorts",
        ],
        ["/product/", "/in/en/pd/"],
        "start",
        0,
        20,
    ),
    (
        "reebok_in",
        "www.reebok.in",
        [
            "https://www.reebok.in/men-t-shirts",
            "https://www.reebok.in/women-t-shirts",
            "https://www.reebok.in/men-shorts",
            "https://www.reebok.in/men-hoodies-and-sweatshirts",
            "https://www.reebok.in/women-hoodies-and-sweatshirts",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "under_armour_in",
        "www.underarmour.in",
        [
            "https://www.underarmour.in/en-in/c/mens-shirts-t-shirts/",
            "https://www.underarmour.in/en-in/c/womens-shirts-t-shirts/",
            "https://www.underarmour.in/en-in/c/mens-shorts/",
            "https://www.underarmour.in/en-in/c/womens-shorts/",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "asics_in",
        "www.asics.co.in",
        [
            "https://www.asics.co.in/men/apparel/t-shirts",
            "https://www.asics.co.in/women/apparel/t-shirts",
            "https://www.asics.co.in/men/apparel/shorts",
            "https://www.asics.co.in/men/apparel/jackets",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "tommy_hilfiger_in",
        "www.tommyhilfiger.in",
        [
            "https://www.tommyhilfiger.in/men/t-shirts",
            "https://www.tommyhilfiger.in/women/t-shirts",
            "https://www.tommyhilfiger.in/men/polos",
            "https://www.tommyhilfiger.in/men/shirts",
            "https://www.tommyhilfiger.in/men/jeans",
            "https://www.tommyhilfiger.in/women/dresses",
            "https://www.tommyhilfiger.in/men/hoodies-sweatshirts",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "calvin_klein_in",
        "www.calvinklein.in",
        [
            "https://www.calvinklein.in/men/tops/t-shirts",
            "https://www.calvinklein.in/women/tops/t-shirts",
            "https://www.calvinklein.in/men/bottoms/jeans",
            "https://www.calvinklein.in/women/bottoms/jeans",
            "https://www.calvinklein.in/men/underwear",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "levis_in",
        "www.levi.in",
        [
            "https://www.levi.in/men/tshirts",
            "https://www.levi.in/women/tshirts",
            "https://www.levi.in/men/shirts",
            "https://www.levi.in/men/jeans",
            "https://www.levi.in/women/jeans",
            "https://www.levi.in/men/shorts",
            "https://www.levi.in/men/joggers",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "benetton_in",
        "www.benetton.in",
        [
            "https://www.benetton.in/men/tshirts",
            "https://www.benetton.in/women/tops",
            "https://www.benetton.in/men/shirts",
            "https://www.benetton.in/women/dresses",
            "https://www.benetton.in/men/jeans",
            "https://www.benetton.in/women/jeans",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "vero_moda_in",
        "www.veromoda.in",
        [
            "https://www.veromoda.in/women/t-shirts",
            "https://www.veromoda.in/women/tops",
            "https://www.veromoda.in/women/dresses",
            "https://www.veromoda.in/women/jeans",
            "https://www.veromoda.in/women/kurtas",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "only_in",
        "www.only.in",
        [
            "https://www.only.in/women/t-shirts",
            "https://www.only.in/women/tops",
            "https://www.only.in/women/dresses",
            "https://www.only.in/women/jeans",
            "https://www.only.in/women/kurtas",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "armani_exchange_com",
        "www.armaniexchange.com",
        [
            "https://www.armaniexchange.com/en_in/category/men/tops/t-shirts",
            "https://www.armaniexchange.com/en_in/category/women/tops",
            "https://www.armaniexchange.com/en_in/category/men/jeans",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "hugo_boss_com",
        "www.hugoboss.com",
        [
            "https://www.hugoboss.com/in/men-t-shirts/",
            "https://www.hugoboss.com/in/women-tops/",
            "https://www.hugoboss.com/in/men-polos/",
            "https://www.hugoboss.com/in/men-shirts/",
            "https://www.hugoboss.com/in/men-jeans/",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "diesel_com",
        "www.diesel.com",
        [
            "https://www.diesel.com/en/men/tops/t-shirts",
            "https://www.diesel.com/en/women/tops",
            "https://www.diesel.com/en/men/jeans",
            "https://www.diesel.com/en/women/jeans",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "superdry_in",
        "www.superdry.in",
        [
            "https://www.superdry.in/mens/t-shirts",
            "https://www.superdry.in/womens/t-shirts",
            "https://www.superdry.in/mens/shirts",
            "https://www.superdry.in/womens/dresses",
            "https://www.superdry.in/mens/hoodies-sweatshirts",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "gap_com",
        "www.gap.com",
        [
            "https://www.gap.com/browse/category.do?cid=5081",
            "https://www.gap.com/browse/category.do?cid=7101",
            "https://www.gap.com/browse/category.do?cid=1080130",
        ],
        ["/browse/product", "/product/"],
        "page",
        1,
        20,
    ),
    (
        "michael_kors_com",
        "www.michaelkors.com",
        [
            "https://www.michaelkors.com/en_in/clothing/t-shirts",
            "https://www.michaelkors.com/en_in/clothing/tops",
            "https://www.michaelkors.com/en_in/handbags",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "coach_com",
        "www.coach.com",
        [
            "https://www.coach.com/content/coach/en_in/womens/bags.html",
            "https://www.coach.com/content/coach/en_in/womens/ready-to-wear.html",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "jockey_in",
        "www.jockey.in",
        [
            "https://www.jockey.in/men/t-shirts",
            "https://www.jockey.in/women/t-shirts",
            "https://www.jockey.in/men/innerwear",
            "https://www.jockey.in/women/innerwear",
            "https://www.jockey.in/men/sports",
            "https://www.jockey.in/women/sports",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "clovia_com",
        "www.clovia.com",
        [
            "https://www.clovia.com/lingerie/",
            "https://www.clovia.com/bra/",
            "https://www.clovia.com/panty/",
            "https://www.clovia.com/nightwear/",
            "https://www.clovia.com/t-shirts-for-women/",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "zivame_com",
        "www.zivame.com",
        [
            "https://www.zivame.com/bra.html",
            "https://www.zivame.com/underwear.html",
            "https://www.zivame.com/lounge.html",
            "https://www.zivame.com/nightwear.html",
            "https://www.zivame.com/sports-bra.html",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "lenskart_com",
        "www.lenskart.com",
        [
            "https://www.lenskart.com/glasses.html",
            "https://www.lenskart.com/sunglasses.html",
            "https://www.lenskart.com/contact-lenses.html",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
    (
        "fastrack_in",
        "www.fastrack.in",
        [
            "https://www.fastrack.in/watches",
            "https://www.fastrack.in/bags",
            "https://www.fastrack.in/accessories",
            "https://www.fastrack.in/sunglasses",
        ],
        ["/product/", "/p/"],
        "page",
        1,
        20,
    ),
]


# ---------------------------------------------------------------------------
# Main setup
# ---------------------------------------------------------------------------

def setup_all():
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)

    yaml_written = []
    py_written = []
    py_skipped = []

    # 1. Update existing PSS sites' YAMLs only (Python kept as-is)
    print("\n=== Updating existing PSS site YAMLs ===")
    for site_name, seeds in EXISTING_PSS_YAMLS:
        yml_path = write_yaml(site_name, seeds, use_proxy=True)
        yaml_written.append(site_name)
        print(f"  [YAML] {yml_path.name}")
        py_skipped.append(site_name)

    # 2. Shopify new sites — YAML + Python
    print("\n=== Writing Shopify sites (YAML + Python) ===")
    for site_name, domain, paths in SHOPIFY_SITES:
        seeds = _shopify_seeds(domain, paths)
        yml_path = write_yaml(site_name, seeds, use_proxy=True)
        yaml_written.append(site_name)

        if site_name not in PROTECTED_PY:
            py_path = write_py_shopify(site_name, domain)
            py_written.append(site_name)
            print(f"  [YAML+PY] {site_name}")
        else:
            py_skipped.append(site_name)
            print(f"  [YAML only, PY protected] {site_name}")

    # 3. Standard querystring new sites — YAML + Python
    print("\n=== Writing Standard querystring sites (YAML + Python) ===")
    for entry in STANDARD_SITES:
        site_name, domain, seeds, product_patterns, pagination_param, pagination_start, pagination_count = entry
        yml_path = write_yaml(site_name, seeds, use_proxy=True)
        yaml_written.append(site_name)

        if site_name not in PROTECTED_PY:
            py_path = write_py_standard(
                site_name=site_name,
                domain=domain,
                product_patterns=product_patterns,
                pagination_param=pagination_param,
                pagination_start=pagination_start,
                pagination_count=pagination_count,
            )
            py_written.append(site_name)
            print(f"  [YAML+PY] {site_name}")
        else:
            py_skipped.append(site_name)
            print(f"  [YAML only, PY protected] {site_name}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  YAMLs written/updated : {len(yaml_written)}")
    print(f"  Python files written  : {len(py_written)}")
    print(f"  Python files skipped  : {len(py_skipped)} (protected)")
    print(f"  Output directory      : {DISCOVERY_DIR}")
    print("=" * 60)
    print("\nDone.")


if __name__ == "__main__":
    setup_all()
