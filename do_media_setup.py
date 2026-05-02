"""
Scaffold / overwrite all media crawl discovery YAML + Python files.
Run: python do_media_setup.py

Existing 11 sites: YAML verified 3-depth, Python protected.
New 66 sites: full YAML + Python written.
"""
from __future__ import annotations
from pathlib import Path

BASE        = Path(__file__).parent
DISC_DIR    = BASE / "url_discovery" / "media_crawl"

# ── Sites whose Python is already well-configured — only YAML update ──────────
PROTECTED_PY = {
    "apparel_resources_com", "business_of_fashion", "drapers_com",
    "fashion_united_global_com", "fashion_united_in", "fibre_2_fashion_com",
    "just_style_com", "the_fashion_law_com", "the_industry_fashion_com",
    "vogue_in", "wwd_com",
}

# ── Shared utility ────────────────────────────────────────────────────────────

def _class_name(site: str) -> str:
    return "".join(w.capitalize() for w in f"{site}_media_crawl".split("_"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [OK] {path.name}")


def write_yaml(site: str, seeds: list[str], use_proxy: bool = False) -> None:
    proxy_block = (
        "\nrequest_params:\n  proxy: webshare_proxy\n  timeout: 30\n  max_retries: 3\n"
        if use_proxy else
        "\nrequest_params:\n  timeout: 30\n  max_retries: 3\n"
    )
    seed_lines = "\n".join(f'    "{s}",' for s in seeds)
    content = (
        f"depth0:\n  seed_url: [\n{seed_lines}\n  ]\n"
        f"depth1:\n  method_name: get_pagination_url\n"
        f"depth2:\n  method_name: get_product_url\n"
        f"{proxy_block}"
    )
    _write(DISC_DIR / f"{site}_media_crawl.yml", content)


def write_py_wordpress(site: str, domain: str, article_paths: list[str],
                       pages: int = 15) -> None:
    """WordPress /page/N/ pagination."""
    cls   = _class_name(site)
    paths = repr(article_paths)
    skip  = repr(["page", "tag", "author", "category", "search", "feed",
                  "topic", "video", "gallery", "photo", "quiz", "newsletter",
                  "wp-content", "wp-json"])
    content = f"""\
from sdf_module.url_discovery import *
from core.discovery_helpers import wordpress_pages
from urllib.parse import urljoin, urlparse
import logging
logger = logging.getLogger(__name__)

DOMAIN        = "{domain}"
ARTICLE_PATHS = {paths}
SKIP_SEGMENTS = {skip}


class {cls}():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += wordpress_pages(keyurl, count={pages})
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
                if len(parts) < 2:
                    continue
                if parts[0] in SKIP_SEGMENTS:
                    continue
                if ARTICLE_PATHS and not any(ap in full for ap in ARTICLE_PATHS):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
"""
    _write(DISC_DIR / f"{site}_media_crawl.py", content)


def write_py_querystring(site: str, domain: str, article_paths: list[str],
                         param: str = "page", pages: int = 15) -> None:
    """Querystring ?param=N pagination."""
    cls   = _class_name(site)
    paths = repr(article_paths)
    skip  = repr(["page", "tag", "author", "category", "search", "feed",
                  "topic", "video", "gallery", "photo", "quiz", "newsletter"])
    content = f"""\
from sdf_module.url_discovery import *
from core.discovery_helpers import querystring_pages
from urllib.parse import urljoin, urlparse
import logging
logger = logging.getLogger(__name__)

DOMAIN        = "{domain}"
ARTICLE_PATHS = {paths}
SKIP_SEGMENTS = {skip}


class {cls}():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        pagination_url = [keyurl]
        try:
            pagination_url += querystring_pages(keyurl, param="{param}", start=2, count={pages})
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
                if len(parts) < 2:
                    continue
                if parts[0] in SKIP_SEGMENTS:
                    continue
                if ARTICLE_PATHS and not any(ap in full for ap in ARTICLE_PATHS):
                    continue
                if full not in seen:
                    seen.add(full)
                    product_url.append(full)
        except Exception as e:
            logger.warning("Exception: %s", e)
        return product_url
"""
    _write(DISC_DIR / f"{site}_media_crawl.py", content)


# ── Site definitions ──────────────────────────────────────────────────────────
#
# Each entry: (seeds, domain, article_paths, pagination_type, param/pages, proxy)
# pagination_type: "wp" | "qs"
# ──────────────────────────────────────────────────────────────────────────────

SITES: dict[str, dict] = {

    # ── Trade publications ────────────────────────────────────────────────────

    "vogue_business_com": dict(
        seeds=[
            "https://www.voguebusiness.com/fashion",
            "https://www.voguebusiness.com/sustainability",
            "https://www.voguebusiness.com/technology",
            "https://www.voguebusiness.com/consumers",
            "https://www.voguebusiness.com/beauty",
        ],
        domain="voguebusiness.com",
        article_paths=["/article/", "/story/"],
        ptype="qs", param="page", pages=10, proxy=True,
    ),

    "retail_dive_com": dict(
        seeds=[
            "https://www.retaildive.com/news/",
            "https://www.retaildive.com/topic/apparel-fashion/",
            "https://www.retaildive.com/topic/ecommerce/",
            "https://www.retaildive.com/topic/retail-technology/",
        ],
        domain="retaildive.com",
        article_paths=["/news/"],
        ptype="wp", pages=12,
    ),

    "internet_retailing_net": dict(
        seeds=[
            "https://internetretailing.net/news/",
            "https://internetretailing.net/themes/fashion/",
            "https://internetretailing.net/themes/marketplace/",
        ],
        domain="internetretailing.net",
        article_paths=[],
        ptype="wp", pages=10,
    ),

    "retail_gazette_com": dict(
        seeds=[
            "https://www.retailgazette.co.uk/blog/",
            "https://www.retailgazette.co.uk/blog/category/fashion/",
            "https://www.retailgazette.co.uk/blog/category/ecommerce/",
        ],
        domain="retailgazette.co.uk",
        article_paths=["/blog/"],
        ptype="wp", pages=12,
    ),

    "fashion_network_com": dict(
        seeds=[
            "https://fashionnetwork.com/news,1.html",
            "https://fashionnetwork.com/news/Brand-strategies,1.html",
            "https://fashionnetwork.com/news/Distribution,1.html",
            "https://fashionnetwork.com/news/India,1.html",
        ],
        domain="fashionnetwork.com",
        article_paths=["/news/"],
        ptype="qs", param="page", pages=12,
    ),

    "india_retailing_com": dict(
        seeds=[
            "https://indiaretailing.com/news/",
            "https://indiaretailing.com/retail/",
            "https://indiaretailing.com/fashion-apparel/",
            "https://indiaretailing.com/ecommerce/",
        ],
        domain="indiaretailing.com",
        article_paths=[],
        ptype="wp", pages=12,
    ),

    "et_retail_com": dict(
        seeds=[
            "https://etretail.com/industry/fashion-/-apparel",
            "https://etretail.com/industry/e-tailing",
            "https://etretail.com/news/",
        ],
        domain="etretail.com",
        article_paths=[],
        ptype="qs", param="page", pages=10,
    ),

    "glossy_com": dict(
        seeds=[
            "https://www.glossy.co/fashion/",
            "https://www.glossy.co/beauty/",
            "https://www.glossy.co/sustainability/",
        ],
        domain="glossy.co",
        article_paths=[],
        ptype="wp", pages=12,
    ),

    # ── Market research & consulting ──────────────────────────────────────────

    "nielsen_com": dict(
        seeds=[
            "https://www.nielsen.com/insights/",
            "https://www.nielsen.com/news-center/",
        ],
        domain="nielsen.com",
        article_paths=["/insights/", "/news-center/"],
        ptype="qs", param="page", pages=8,
    ),

    "kantar_com": dict(
        seeds=[
            "https://www.kantar.com/inspiration/",
            "https://www.kantar.com/company/news-and-press-releases/",
        ],
        domain="kantar.com",
        article_paths=["/inspiration/", "/company/news"],
        ptype="qs", param="page", pages=8,
    ),

    "redseer_com": dict(
        seeds=[
            "https://redseer.com/reports/",
            "https://redseer.com/newsletters/",
            "https://redseer.com/podcasts/",
        ],
        domain="redseer.com",
        article_paths=["/reports/", "/newsletters/"],
        ptype="wp", pages=6,
    ),

    "technopak_com": dict(
        seeds=[
            "https://technopak.com/resources/",
            "https://technopak.com/publications/",
        ],
        domain="technopak.com",
        article_paths=[],
        ptype="wp", pages=5,
    ),

    "mintel_com": dict(
        seeds=[
            "https://www.mintel.com/press-centre/",
            "https://www.mintel.com/insights/",
        ],
        domain="mintel.com",
        article_paths=["/press-centre/", "/insights/"],
        ptype="wp", pages=8,
    ),

    "euromonitor_com": dict(
        seeds=[
            "https://www.euromonitor.com/articles",
            "https://www.euromonitor.com/insights",
        ],
        domain="euromonitor.com",
        article_paths=["/articles/", "/insights/"],
        ptype="qs", param="page", pages=8,
    ),

    # ── India business news ───────────────────────────────────────────────────

    "economic_times_com": dict(
        seeds=[
            "https://economictimes.indiatimes.com/industry/services/retail",
            "https://economictimes.indiatimes.com/industry/cons-products/fashion-/-cosmetics",
            "https://economictimes.indiatimes.com/industry/cons-products/garments-/-textiles",
            "https://economictimes.indiatimes.com/small-biz/startups/newsbuzz",
        ],
        domain="economictimes.indiatimes.com",
        article_paths=["/articleshow/", "/news/"],
        ptype="qs", param="curpg", pages=10,
    ),

    "business_standard_com": dict(
        seeds=[
            "https://www.business-standard.com/industry/fashion-textile",
            "https://www.business-standard.com/companies/retail",
            "https://www.business-standard.com/economy/news",
        ],
        domain="business-standard.com",
        article_paths=["/article/", "/companies/", "/industry/"],
        ptype="qs", param="pageNumber", pages=10,
    ),

    "financial_express_com": dict(
        seeds=[
            "https://www.financialexpress.com/industry/",
            "https://www.financialexpress.com/jobs-career/",
            "https://www.financialexpress.com/business/",
        ],
        domain="financialexpress.com",
        article_paths=["/industry/", "/business/"],
        ptype="qs", param="page", pages=10,
    ),

    "livemint_com": dict(
        seeds=[
            "https://www.livemint.com/fashion",
            "https://www.livemint.com/companies/retail",
            "https://www.livemint.com/industry",
        ],
        domain="livemint.com",
        article_paths=["/fashion/", "/companies/", "/industry/"],
        ptype="qs", param="page", pages=10,
    ),

    "mint_com": dict(
        seeds=[
            "https://www.livemint.com/fashion",
            "https://www.livemint.com/companies/retail",
        ],
        domain="livemint.com",
        article_paths=["/fashion/", "/companies/"],
        ptype="qs", param="page", pages=8,
    ),

    "business_today_in": dict(
        seeds=[
            "https://www.businesstoday.in/latest/",
            "https://www.businesstoday.in/lifestyle/",
            "https://www.businesstoday.in/magazine/",
        ],
        domain="businesstoday.in",
        article_paths=["/latest/", "/story/", "/lifestyle/"],
        ptype="qs", param="page", pages=10,
    ),

    "hindustan_times_com": dict(
        seeds=[
            "https://www.hindustantimes.com/lifestyle/fashion",
            "https://www.hindustantimes.com/business",
        ],
        domain="hindustantimes.com",
        article_paths=["/lifestyle/", "/business/"],
        ptype="qs", param="page", pages=10,
    ),

    "indian_express_com": dict(
        seeds=[
            "https://indianexpress.com/lifestyle/fashion/",
            "https://indianexpress.com/section/business/",
            "https://indianexpress.com/section/lifestyle/",
        ],
        domain="indianexpress.com",
        article_paths=["/article/"],
        ptype="qs", param="page", pages=10,
    ),

    "the_hindu_com": dict(
        seeds=[
            "https://www.thehindu.com/fashion/",
            "https://www.thehindu.com/business/",
            "https://www.thehindu.com/life-and-style/",
        ],
        domain="thehindu.com",
        article_paths=["/article/"],
        ptype="qs", param="page", pages=10,
    ),

    "times_of_india_com": dict(
        seeds=[
            "https://timesofindia.indiatimes.com/life-style/fashion",
            "https://timesofindia.indiatimes.com/business/india-business",
            "https://timesofindia.indiatimes.com/life-style/fashion/style-tips",
        ],
        domain="timesofindia.indiatimes.com",
        article_paths=["/articleshow/"],
        ptype="qs", param="curpg", pages=10,
    ),

    "scroll_in": dict(
        seeds=[
            "https://scroll.in/latest",
            "https://scroll.in/article",
        ],
        domain="scroll.in",
        article_paths=["/article/"],
        ptype="qs", param="page", pages=10,
    ),

    "business_insider_in": dict(
        seeds=[
            "https://www.businessinsider.in/retail/",
            "https://www.businessinsider.in/business/",
            "https://www.businessinsider.in/tech/",
        ],
        domain="businessinsider.in",
        article_paths=["/articleshow/", "/article/"],
        ptype="qs", param="page", pages=10,
    ),

    # ── India startup media ───────────────────────────────────────────────────

    "yourstory_com": dict(
        seeds=[
            "https://yourstory.com/tag/fashion",
            "https://yourstory.com/tag/ecommerce",
            "https://yourstory.com/tag/d2c",
            "https://yourstory.com/tag/retail",
        ],
        domain="yourstory.com",
        article_paths=["/story/", "/company/"],
        ptype="qs", param="page", pages=10,
    ),

    "inc42_com": dict(
        seeds=[
            "https://inc42.com/buzz/ecommerce/",
            "https://inc42.com/features/d2c/",
            "https://inc42.com/tag/fashion/",
            "https://inc42.com/buzz/retail/",
        ],
        domain="inc42.com",
        article_paths=["/buzz/", "/features/", "/startups/"],
        ptype="qs", param="page", pages=10,
    ),

    "entrepreneur_com": dict(
        seeds=[
            "https://www.entrepreneur.com/topic/fashion",
            "https://www.entrepreneur.com/topic/retail",
            "https://www.entrepreneur.com/topic/ecommerce",
        ],
        domain="entrepreneur.com",
        article_paths=["/article/", "/slideshow/"],
        ptype="qs", param="page", pages=10,
    ),

    # ── India fashion magazines ───────────────────────────────────────────────

    "grazia_in": dict(
        seeds=[
            "https://www.grazia.co.in/fashion/",
            "https://www.grazia.co.in/style/",
            "https://www.grazia.co.in/celebrity/",
        ],
        domain="grazia.co.in",
        article_paths=["/fashion/", "/style/", "/celebrity/"],
        ptype="wp", pages=10,
    ),

    "cosmopolitan_in": dict(
        seeds=[
            "https://www.cosmopolitan.in/fashion/",
            "https://www.cosmopolitan.in/style-advice/",
            "https://www.cosmopolitan.in/celebrity/",
        ],
        domain="cosmopolitan.in",
        article_paths=["/fashion/", "/style-advice/"],
        ptype="wp", pages=10,
    ),

    "elle_in": dict(
        seeds=[
            "https://www.elle.in/fashion/",
            "https://www.elle.in/style/",
            "https://www.elle.in/celebrity/",
            "https://www.elle.in/beauty/",
        ],
        domain="elle.in",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=10, proxy=True,
    ),

    "gq_india_com": dict(
        seeds=[
            "https://www.gqindia.com/fashion/",
            "https://www.gqindia.com/style/",
            "https://www.gqindia.com/grooming/",
            "https://www.gqindia.com/content/",
        ],
        domain="gqindia.com",
        article_paths=["/fashion/", "/style/", "/content/"],
        ptype="qs", param="page", pages=10, proxy=True,
    ),

    "femina_in": dict(
        seeds=[
            "https://www.femina.in/fashion/",
            "https://www.femina.in/style-files/",
            "https://www.femina.in/trending/",
        ],
        domain="femina.in",
        article_paths=["/fashion/", "/style-files/", "/trending/"],
        ptype="wp", pages=10,
    ),

    "harpers_bazaar_in": dict(
        seeds=[
            "https://www.harpersbazaar.in/fashion/",
            "https://www.harpersbazaar.in/style/",
            "https://www.harpersbazaar.in/celebrity/",
        ],
        domain="harpersbazaar.in",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=10, proxy=True,
    ),

    "lofficiel_india_com": dict(
        seeds=[
            "https://www.lofficielindia.com/fashion/",
            "https://www.lofficielindia.com/culture/",
            "https://www.lofficielindia.com/beauty/",
        ],
        domain="lofficielindia.com",
        article_paths=["/fashion/", "/culture/"],
        ptype="qs", param="page", pages=8,
    ),

    "mans_world_india_com": dict(
        seeds=[
            "https://www.mansworldindia.com/fashion/",
            "https://www.mansworldindia.com/style/",
            "https://www.mansworldindia.com/grooming/",
        ],
        domain="mansworldindia.com",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=8,
    ),

    "brides_today_in": dict(
        seeds=[
            "https://www.bridestoday.in/fashion/",
            "https://www.bridestoday.in/bridal-wear/",
            "https://www.bridestoday.in/wedding-trends/",
            "https://www.bridestoday.in/lehenga/",
        ],
        domain="bridestoday.in",
        article_paths=["/fashion/", "/bridal-wear/", "/wedding-trends/"],
        ptype="wp", pages=8,
    ),

    "the_voice_of_fashion_com": dict(
        seeds=[
            "https://www.thevoiceoffashion.com/stories/",
            "https://www.thevoiceoffashion.com/runway/",
            "https://www.thevoiceoffashion.com/news/",
        ],
        domain="thevoiceoffashion.com",
        article_paths=["/stories/", "/runway/", "/news/"],
        ptype="wp", pages=8,
    ),

    "instyle_in": dict(
        seeds=[
            "https://www.instyle.co.in/fashion/",
            "https://www.instyle.co.in/style/",
            "https://www.instyle.co.in/celebrity/",
        ],
        domain="instyle.co.in",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=8,
    ),

    # ── Global fashion magazines ──────────────────────────────────────────────

    "vogue_com": dict(
        seeds=[
            "https://www.vogue.com/fashion",
            "https://www.vogue.com/style",
            "https://www.vogue.com/fashion/trends",
            "https://www.vogue.com/street-style",
        ],
        domain="vogue.com",
        article_paths=["/article/", "/story/"],
        ptype="qs", param="page", pages=10, proxy=True,
    ),

    "elle_com": dict(
        seeds=[
            "https://www.elle.com/fashion/",
            "https://www.elle.com/style/",
            "https://www.elle.com/fashion/trend-reports/",
            "https://www.elle.com/fashion/celebrity-style/",
        ],
        domain="elle.com",
        article_paths=["/fashion/", "/style/"],
        ptype="qs", param="page", pages=10, proxy=True,
    ),

    "harpers_bazaar_com": dict(
        seeds=[
            "https://www.harpersbazaar.com/fashion/",
            "https://www.harpersbazaar.com/fashion/trends/",
            "https://www.harpersbazaar.com/fashion/designers/",
            "https://www.harpersbazaar.com/fashion/street-style/",
        ],
        domain="harpersbazaar.com",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=10, proxy=True,
    ),

    "nylon_com": dict(
        seeds=[
            "https://www.nylon.com/fashion/",
            "https://www.nylon.com/style/",
            "https://www.nylon.com/celebrity/",
        ],
        domain="nylon.com",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=10,
    ),

    "paper_mag_com": dict(
        seeds=[
            "https://www.papermag.com/fashion/",
            "https://www.papermag.com/style/",
        ],
        domain="papermag.com",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=8,
    ),

    "gq_com": dict(
        seeds=[
            "https://www.gq.com/style",
            "https://www.gq.com/fashion",
            "https://www.gq.com/grooming",
        ],
        domain="gq.com",
        article_paths=["/style/", "/fashion/", "/story/"],
        ptype="qs", param="page", pages=10, proxy=True,
    ),

    # ── Consumer fashion sites ────────────────────────────────────────────────

    "popsugar_com": dict(
        seeds=[
            "https://www.popsugar.com/fashion/",
            "https://www.popsugar.com/fashion/trend/",
            "https://www.popsugar.com/fashion/celebrity-style/",
        ],
        domain="popsugar.com",
        article_paths=["/fashion/", "/photo-gallery/"],
        ptype="qs", param="page", pages=10,
    ),

    "who_what_wear_com": dict(
        seeds=[
            "https://www.whowhatwear.com/fashion/",
            "https://www.whowhatwear.com/trends/",
            "https://www.whowhatwear.com/celebrities-and-fashion/",
        ],
        domain="whowhatwear.com",
        article_paths=["/fashion/", "/trends/"],
        ptype="qs", param="page", pages=10,
    ),

    "refinery29_com": dict(
        seeds=[
            "https://www.refinery29.com/en-us/fashion",
            "https://www.refinery29.com/en-us/style",
            "https://www.refinery29.com/en-us/shopping",
        ],
        domain="refinery29.com",
        article_paths=["/en-us/"],
        ptype="qs", param="page", pages=10,
    ),

    "fashionista_com": dict(
        seeds=[
            "https://fashionista.com/",
            "https://fashionista.com/category/fashion",
            "https://fashionista.com/category/retail",
        ],
        domain="fashionista.com",
        article_paths=[],
        ptype="wp", pages=12,
    ),

    "style_caster_com": dict(
        seeds=[
            "https://stylecaster.com/fashion/",
            "https://stylecaster.com/style/",
            "https://stylecaster.com/fashion/celebrity-style/",
        ],
        domain="stylecaster.com",
        article_paths=["/fashion/", "/style/"],
        ptype="wp", pages=10,
    ),

    "the_trend_spotter_com": dict(
        seeds=[
            "https://www.trendspotter.net/fashion-trends/",
            "https://www.trendspotter.net/mens-fashion/",
            "https://www.trendspotter.net/womens-fashion/",
        ],
        domain="trendspotter.net",
        article_paths=["/fashion-trends/", "/mens-fashion/", "/womens-fashion/"],
        ptype="wp", pages=10,
    ),

    # ── Streetwear / culture ──────────────────────────────────────────────────

    "highsnobiety_com": dict(
        seeds=[
            "https://www.highsnobiety.com/style/",
            "https://www.highsnobiety.com/sneakers/",
            "https://www.highsnobiety.com/fashion/",
            "https://www.highsnobiety.com/streetwear/",
        ],
        domain="highsnobiety.com",
        article_paths=["/style/", "/sneakers/", "/fashion/"],
        ptype="qs", param="page", pages=10,
    ),

    "hypebeast_com": dict(
        seeds=[
            "https://hypebeast.com/fashion",
            "https://hypebeast.com/footwear",
            "https://hypebeast.com/lifestyle",
            "https://hypebeasts.com/india",
        ],
        domain="hypebeast.com",
        article_paths=["/fashion/", "/footwear/", "/lifestyle/"],
        ptype="qs", param="page", pages=10,
    ),

    # ── Global business press ─────────────────────────────────────────────────

    "forbes_com": dict(
        seeds=[
            "https://www.forbes.com/fashion/",
            "https://www.forbes.com/retail/",
            "https://www.forbes.com/innovation/",
        ],
        domain="forbes.com",
        article_paths=["/sites/"],
        ptype="qs", param="page", pages=8, proxy=True,
    ),

    "bloomberg_com": dict(
        seeds=[
            "https://www.bloomberg.com/fashion",
            "https://www.bloomberg.com/industries/retailing",
        ],
        domain="bloomberg.com",
        article_paths=["/news/articles/", "/news/features/"],
        ptype="qs", param="page", pages=6, proxy=True,
    ),

    "fast_company_com": dict(
        seeds=[
            "https://www.fastcompany.com/section/retail/",
            "https://www.fastcompany.com/section/fashion/",
            "https://www.fastcompany.com/section/technology/",
        ],
        domain="fastcompany.com",
        article_paths=["/article/", "/content/"],
        ptype="qs", param="page", pages=8,
    ),

    "vox_com": dict(
        seeds=[
            "https://www.vox.com/the-goods/fashion",
            "https://www.vox.com/recode",
        ],
        domain="vox.com",
        article_paths=["/the-goods/", "/recode/"],
        ptype="qs", param="page", pages=8,
    ),

    "business_insider_com": dict(
        seeds=[
            "https://www.businessinsider.com/retail/",
            "https://www.businessinsider.com/ecommerce/",
            "https://www.businessinsider.com/fashion/",
        ],
        domain="businessinsider.com",
        article_paths=["/retail/", "/ecommerce/", "/fashion/"],
        ptype="qs", param="page", pages=8,
    ),

    # ── Global news ───────────────────────────────────────────────────────────

    "the_guardian_com": dict(
        seeds=[
            "https://www.theguardian.com/fashion",
            "https://www.theguardian.com/business/retail-industry",
            "https://www.theguardian.com/fashion/india",
        ],
        domain="theguardian.com",
        article_paths=["/fashion/", "/business/"],
        ptype="qs", param="page", pages=10,
    ),

    "cnn_com": dict(
        seeds=[
            "https://edition.cnn.com/style/fashion",
            "https://edition.cnn.com/style",
            "https://edition.cnn.com/business/retail",
        ],
        domain="cnn.com",
        article_paths=["/style/", "/business/"],
        ptype="qs", param="page", pages=8,
    ),

    "bbc_com": dict(
        seeds=[
            "https://www.bbc.com/culture/fashion",
            "https://www.bbc.com/news/business",
        ],
        domain="bbc.com",
        article_paths=["/culture/fashion/", "/news/"],
        ptype="qs", param="page", pages=8,
    ),

    # ── Tech / commerce tech ──────────────────────────────────────────────────

    "the_verge_com": dict(
        seeds=[
            "https://www.theverge.com/fashion/",
            "https://www.theverge.com/retail/",
            "https://www.theverge.com/ecommerce/",
        ],
        domain="theverge.com",
        article_paths=["/fashion/", "/retail/"],
        ptype="qs", param="page", pages=8,
    ),

    "techcrunch_com": dict(
        seeds=[
            "https://techcrunch.com/tag/fashion/",
            "https://techcrunch.com/tag/ecommerce/",
            "https://techcrunch.com/commerce/",
        ],
        domain="techcrunch.com",
        article_paths=["/"],
        ptype="qs", param="page", pages=8,
    ),

    "wired_com": dict(
        seeds=[
            "https://www.wired.com/tag/fashion/",
            "https://www.wired.com/tag/ecommerce/",
            "https://www.wired.com/business/",
        ],
        domain="wired.com",
        article_paths=["/story/", "/article/"],
        ptype="wp", pages=8,
    ),

    # ── India local / discovery ───────────────────────────────────────────────

    "lbb_in": dict(
        seeds=[
            "https://lbb.in/mumbai/fashion/",
            "https://lbb.in/delhi/fashion/",
            "https://lbb.in/bangalore/fashion/",
            "https://lbb.in/mumbai/",
        ],
        domain="lbb.in",
        article_paths=["/fashion/", "/style/"],
        ptype="qs", param="page", pages=8,
    ),
}


# ── Runner ────────────────────────────────────────────────────────────────────

def setup_all() -> None:
    yaml_count = py_count = skip_count = 0

    print(f"\n=== Updating existing 11 media site YAMLs (Python protected) ===")
    # Their YAMLs were fixed to 3-depth earlier — just confirm the files are
    # correct by re-reading; no overwrite needed unless seeds change.
    for site in PROTECTED_PY:
        yml = DISC_DIR / f"{site}_media_crawl.yml"
        if yml.exists():
            text = yml.read_text(encoding="utf-8")
            if "depth1:" in text and "depth2:" in text:
                print(f"  [OK] {site} — 3-depth confirmed")
            else:
                print(f"  [!!] {site} — still 2-depth, needs manual fix")

    print(f"\n=== Writing {len(SITES)} new media sites ===")
    for site, cfg in SITES.items():
        seeds    = cfg["seeds"]
        domain   = cfg["domain"]
        apaths   = cfg.get("article_paths", [])
        ptype    = cfg.get("ptype", "wp")
        param    = cfg.get("param", "page")
        pages    = cfg.get("pages", 12)
        proxy    = cfg.get("proxy", False)

        print(f"\n  [{site}]")
        write_yaml(site, seeds, use_proxy=proxy)
        yaml_count += 1

        if site in PROTECTED_PY:
            print(f"  [SKIP] {site} Python protected")
            skip_count += 1
            continue

        if ptype == "wp":
            write_py_wordpress(site, domain, apaths, pages=pages)
        else:
            write_py_querystring(site, domain, apaths, param=param, pages=pages)
        py_count += 1

    print(f"""
{'='*60}
SUMMARY
{'='*60}
  YAMLs written   : {yaml_count}
  Python written  : {py_count}
  Python skipped  : {skip_count} (protected)
  Output dir      : {DISC_DIR}
{'='*60}
""")


if __name__ == "__main__":
    setup_all()
