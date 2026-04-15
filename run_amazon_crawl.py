"""
Standalone Amazon crawl runner.

Fetches Amazon.in search results → product pages → extracts structured data.

Strategy ladder (auto-escalates if blocked):
  1. requests + webshare proxy   (fast, cheap)
  2. Playwright (Chromium)       (bypasses JS challenges / fingerprinting)
  3. Playwright via DuckDuckGo   (searches DDG for the ASIN and navigates)
  4. Playwright via Google       (last resort search fallback)

Usage:
    python run_amazon_crawl.py
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import random
from pathlib import Path
from urllib.parse import urlparse, urljoin

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Load .env before importing any SARA modules
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── imports ───────────────────────────────────────────────────────────────────
import requests
from lxml import html

import io as _io
_stdout_utf8 = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(_stdout_utf8)],
)
logger = logging.getLogger("amazon_crawl")

# ── config ────────────────────────────────────────────────────────────────────
SEED_URLS = [
    "https://www.amazon.in/s?k=men+t+shirts&rh=n%3A1968024031",
    "https://www.amazon.in/s?k=women+t+shirts&rh=n%3A1968024031",
    "https://www.amazon.in/s?k=men+polo+shirts&rh=n%3A1968024031",
]
MAX_PAGES_PER_SEED = 3       # pagination pages per seed URL
MAX_PRODUCTS       = 20      # total products to parse
OUTPUT_FILE        = ROOT / "amazon_crawl_results.json"

# Strip ref= and query params from product URLs — deduplicate by /dp/ASIN/
def _clean_product_url(url: str) -> str:
    """Return a canonical Amazon product URL with just the ASIN path."""
    m = re.search(r"(https?://www\.amazon\.in(?:/[^/]+)?/dp/[A-Z0-9]{10})", url)
    if m:
        return m.group(1) + "/"
    # fallback — strip query string
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# ── proxy setup ───────────────────────────────────────────────────────────────
_PROXY_RAW = os.environ.get("WEBSHARE_PROXY_JSON", "[]")
try:
    _PROXIES_LIST = json.loads(_PROXY_RAW)
except Exception:
    _PROXIES_LIST = []

def _random_proxy() -> dict | None:
    if not _PROXIES_LIST:
        return None
    host, port, user, pwd = random.choice(_PROXIES_LIST)
    url = f"http://{user}:{pwd}@{host}:{port}"
    return {"http": url, "https": url}


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 1 — direct requests with proxy
# ─────────────────────────────────────────────────────────────────────────────

def fetch_direct(url: str, retries: int = 3) -> tuple[str | None, int]:
    """Return (html_text, status_code). Returns None html on block/failure."""
    proxies = _random_proxy()
    for attempt in range(retries):
        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=30,
                allow_redirects=True,
            )
            code = resp.status_code
            if code == 200:
                text = resp.text
                # Quick block detection
                if any(p in text.lower() for p in (
                    "checking your browser", "enable javascript and cookies",
                    "cf-turnstile", "robot check", "captcha", "sorry, we just need"
                )):
                    logger.warning("Block page detected at %s (status 200)", url)
                    return None, 200
                return text, 200
            if code in (403, 429, 503):
                logger.warning("Blocked (HTTP %d) on attempt %d for %s", code, attempt + 1, url)
                proxies = _random_proxy()   # rotate proxy
                time.sleep(2 ** attempt)
                continue
            logger.warning("HTTP %d for %s", code, url)
            return None, code
        except Exception as exc:
            logger.warning("Request error (attempt %d): %s", attempt + 1, exc)
            proxies = _random_proxy()
            time.sleep(2 ** attempt)
    return None, 0


# ─────────────────────────────────────────────────────────────────────────────
# Strategy 2/3/4 — Playwright fallback
# ─────────────────────────────────────────────────────────────────────────────

def _playwright_get(page, url: str, wait_ms: int = 3000, timeout_ms: int = 60_000) -> str | None:
    """Navigate to url and return page HTML, or None on error."""
    try:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_ms)
        html_text = page.content()
        if any(p in html_text.lower() for p in (
            "captcha", "are you a robot", "verify you are human"
        )):
            logger.warning("CAPTCHA wall at %s — cannot bypass automatically", url)
            return None
        return html_text
    except Exception as exc:
        logger.warning("Playwright navigation error: %s", exc)
        return None


def _make_playwright_browser(p, headless=True):
    """Launch Chromium without proxy — proxy auth is unreliable; go direct."""
    browser = p.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        user_agent=HEADERS["User-Agent"],
        locale="en-US",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    # Hide webdriver flag
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, ctx


def fetch_playwright(url: str) -> tuple[str | None, int]:
    """Strategy 2: open URL directly in Chromium (no proxy — avoids 407 errors)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright not installed")
        return None, 0

    logger.info("Using Playwright (direct) for %s", url)
    try:
        with sync_playwright() as p:
            browser, ctx = _make_playwright_browser(p)
            page = ctx.new_page()
            html_text = _playwright_get(page, url, wait_ms=4000, timeout_ms=60_000)
            browser.close()
        if html_text:
            return html_text, 200
    except Exception as exc:
        logger.warning("Playwright launch error: %s", exc)
    return None, 0


def fetch_via_search_engine(asin_or_query: str, engine: str = "duckduckgo") -> tuple[str | None, int]:
    """
    Strategy 3/4: search DuckDuckGo or Google for the ASIN,
    extract the direct Amazon.in URL from search results, then navigate to it.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, 0

    if engine == "duckduckgo":
        search_url = f"https://duckduckgo.com/?q=amazon.in+{asin_or_query}&kl=in-en"
    else:
        search_url = f"https://www.google.com/search?q=site:amazon.in+{asin_or_query}"

    logger.info("Using Playwright + %s to find: %s", engine, asin_or_query)

    try:
        with sync_playwright() as p:
            browser, ctx = _make_playwright_browser(p)
            page = ctx.new_page()

            page.goto(search_url, timeout=25_000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            # Collect all hrefs from the page
            hrefs = page.eval_on_selector_all(
                "a",
                "els => els.map(e => e.href)",
            )

            amazon_url = None
            for href in hrefs:
                href = str(href)
                if "amazon.in" in href and ("/dp/" in href or "/gp/product/" in href):
                    amazon_url = _clean_product_url(href)
                    break

            if not amazon_url:
                # Try extracting from text (Google wraps links)
                content = page.content()
                matches = re.findall(
                    r'https?://(?:www\.)?amazon\.in[^\s"\'<>]*?/dp/[A-Z0-9]{10}[^\s"\'<>]*',
                    content,
                )
                if matches:
                    amazon_url = _clean_product_url(matches[0])

            if not amazon_url:
                logger.warning("No Amazon link found in %s results for %s", engine, asin_or_query)
                browser.close()
                return None, 0

            logger.info("Found via %s: %s", engine, amazon_url)
            html_text = _playwright_get(page, amazon_url, wait_ms=4000, timeout_ms=60_000)
            browser.close()
            if html_text:
                return html_text, 200
    except Exception as exc:
        logger.warning("Search-engine (%s) strategy error: %s", engine, exc)
    return None, 0


def fetch_with_fallback(url: str) -> str | None:
    """Try all strategies in order, return HTML or None."""
    # Strategy 1: direct + proxy
    html_text, code = fetch_direct(url)
    if html_text:
        logger.info("Strategy 1 (direct) succeeded for %s", url)
        return html_text

    # Strategy 2: Playwright direct
    logger.info("Direct fetch failed — trying Playwright")
    html_text, code = fetch_playwright(url)
    if html_text:
        logger.info("Strategy 2 (Playwright) succeeded for %s", url)
        return html_text

    # Strategy 3: DuckDuckGo search
    # Extract ASIN from URL if present
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    query = m.group(1) if m else urlparse(url).path.strip("/").replace("/", " ")
    logger.info("Playwright failed — trying DuckDuckGo search")
    html_text, code = fetch_via_search_engine(query, engine="duckduckgo")
    if html_text:
        logger.info("Strategy 3 (DuckDuckGo) succeeded for %s", url)
        return html_text

    # Strategy 4: Google search
    logger.info("DuckDuckGo failed — trying Google search")
    html_text, code = fetch_via_search_engine(query, engine="google")
    if html_text:
        logger.info("Strategy 4 (Google) succeeded for %s", url)
        return html_text

    logger.error("All strategies exhausted for %s", url)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Discovery — find product URLs from search pages
# ─────────────────────────────────────────────────────────────────────────────

def get_product_urls_from_page(html_text: str, base: str = "https://www.amazon.in") -> list[str]:
    tree = html.fromstring(html_text)

    # Multiple XPath strategies for Amazon's varying markup
    hrefs = (
        tree.xpath("//div[@data-component-type='s-search-result']//h2/a/@href")
        or tree.xpath("//div[@data-component-type='s-search-result']//a[contains(@class,'a-link-normal') and contains(@href,'/dp/')]/@href")
        or tree.xpath("//div[@data-asin and string-length(@data-asin)>0]//h2/a/@href")
        or tree.xpath("//a[contains(@href,'/dp/') and contains(@class,'a-link-normal')]/@href")
    )

    # Also try extracting ASINs from data-asin attributes directly (works when Playwright renders)
    asins = tree.xpath("//div[@data-asin and string-length(@data-asin)>0]/@data-asin")

    seen_asins: set[str] = set()
    urls: list[str] = []

    # From href list
    for href in hrefs:
        if not href:
            continue
        full = base + href if href.startswith("/") else href
        if "amazon.in" not in full:
            continue
        # Canonicalise to /dp/ASIN/ and deduplicate by ASIN
        canonical = _clean_product_url(full)
        m = re.search(r"/dp/([A-Z0-9]{10})", canonical)
        if not m:
            continue
        asin = m.group(1)
        if asin not in seen_asins:
            seen_asins.add(asin)
            urls.append(canonical)

    # From data-asin attributes (Playwright-rendered pages)
    for asin in asins:
        asin = asin.strip()
        if asin and asin not in seen_asins:
            seen_asins.add(asin)
            urls.append(f"https://www.amazon.in/dp/{asin}/")

    return urls


def discover_product_urls() -> list[str]:
    all_urls: list[str] = []
    for seed in SEED_URLS:
        logger.info("Discovering from seed: %s", seed)
        html_text = fetch_with_fallback(seed)
        if not html_text:
            logger.warning("Could not fetch seed: %s", seed)
            continue

        urls = get_product_urls_from_page(html_text)
        logger.info("Found %d products on page 1 of %s", len(urls), seed)
        all_urls.extend(urls)

        # Pagination
        for page in range(2, MAX_PAGES_PER_SEED + 1):
            page_url = f"{seed}&page={page}"
            logger.info("Fetching page %d: %s", page, page_url)
            page_html = fetch_with_fallback(page_url)
            if not page_html:
                break
            page_urls = get_product_urls_from_page(page_html)
            logger.info("Found %d products on page %d", len(page_urls), page)
            all_urls.extend(page_urls)
            if not page_urls:
                break
            time.sleep(1)

        if len(all_urls) >= MAX_PRODUCTS * 2:
            break

    # Deduplicate
    seen: set[str] = set()
    deduped: list[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    logger.info("Total unique product URLs discovered: %d", len(deduped))
    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# Parser — extract structured data
# ─────────────────────────────────────────────────────────────────────────────

def parse_product(html_text: str, url: str) -> dict:
    tree = html.fromstring(html_text)

    def first(xpaths: list[str]) -> str | None:
        for xp in xpaths:
            vals = tree.xpath(xp)
            if vals:
                text = vals[0].strip() if isinstance(vals[0], str) else ""
                if text:
                    return text
        return None

    def to_int(s: str | None) -> int | None:
        if not s:
            return None
        cleaned = re.sub(r"[^\d]", "", s)
        return int(cleaned) if cleaned else None

    product_name = first([
        "//span[@id='productTitle']/text()",
        "//h1[@id='title']//span/text()",
    ])

    # List price
    list_price_raw = first([
        "//span[@class='a-price a-text-price a-size-medium']/span/text()",
        "//span[contains(@class,'a-price a-text-price')]/span[@class='a-offscreen']/text()",
        "//td[contains(@class,'a-color-secondary')]//span[@class='a-offscreen']/text()",
    ])

    # Selling price
    selling_price_raw = first([
        "//span[@id='priceblock_ourprice']/text()",
        "//span[@id='priceblock_dealprice']/text()",
        "//span[contains(@class,'priceToPay')]//span[@class='a-offscreen']/text()",
        "//span[@class='a-price aok-align-center reinventPricePriceToPayMargin priceToPay']//span[@class='a-offscreen']/text()",
        "//div[@id='corePrice_feature_div']//span[@class='a-offscreen']/text()",
    ])

    # Discount
    discount_raw = first([
        "//span[contains(@class,'savingsPercentage')]/text()",
        "//td[@class='a-span12 a-color-price a-size-base']//text()",
    ])
    discount_pct = None
    if discount_raw:
        m = re.search(r"(\d+)\s*%", discount_raw)
        if m:
            discount_pct = int(m.group(1))

    # ASIN
    asin = first(["//th[text()='ASIN']/following-sibling::td/text()"])
    if not asin:
        m = re.search(r"/dp/([A-Z0-9]{10})", url)
        asin = m.group(1) if m else None

    size = first([
        "//span[@id='native_dropdown_selected_size_name']/text()",
        "//div[@id='variation_size_name']//span[@class='selection']/text()",
    ])

    color = first([
        "//span[@id='variation_color_name']//span[@class='selection']/text()",
        "//div[@id='variation_color_name']//span[@class='selection']/text()",
    ])

    description_parts = tree.xpath("//div[@id='productDescription']//text()")
    description = " ".join(t.strip() for t in description_parts if t.strip()) or None

    # Rating
    rating = first([
        "//span[@id='acrPopover']/@title",
        "//span[contains(@class,'a-icon-alt')]/text()",
    ])

    # Reviews count
    reviews_raw = first([
        "//span[@id='acrCustomerReviewText']/text()",
    ])
    reviews_count = None
    if reviews_raw:
        m = re.search(r"([\d,]+)", reviews_raw)
        if m:
            reviews_count = int(m.group(1).replace(",", ""))

    # Brand
    brand = first([
        "//a[@id='bylineInfo']/text()",
        "//span[@id='brand']/text()",
        "//tr[th[text()='Brand']]/td/text()",
    ])

    return {
        "url": url,
        "asin": asin,
        "product_name": product_name,
        "brand": brand,
        "selling_price": to_int(selling_price_raw),
        "list_price": to_int(list_price_raw),
        "discount_percentage": discount_pct,
        "size": size,
        "color": color,
        "rating": rating,
        "reviews_count": reviews_count,
        "description": (description[:300] + "…") if description and len(description) > 300 else description,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("Amazon.in crawl starting")
    logger.info("Seeds: %d  |  Max pages/seed: %d  |  Max products: %d",
                len(SEED_URLS), MAX_PAGES_PER_SEED, MAX_PRODUCTS)
    logger.info("=" * 60)

    # Stage 1: Discovery
    product_urls = discover_product_urls()
    if not product_urls:
        logger.error("Discovery returned 0 product URLs — aborting")
        sys.exit(1)

    # Limit to MAX_PRODUCTS
    product_urls = product_urls[:MAX_PRODUCTS]
    logger.info("Will parse %d products", len(product_urls))

    # Stage 2: Fetch + Parse
    results: list[dict] = []
    for i, url in enumerate(product_urls, 1):
        logger.info("[%d/%d] Fetching product: %s", i, len(product_urls), url)
        html_text = fetch_with_fallback(url)
        if not html_text:
            logger.warning("Skipping %s — all strategies failed", url)
            results.append({"url": url, "error": "fetch_failed"})
            continue

        try:
            data = parse_product(html_text, url)
            results.append(data)
            logger.info(
                "  Parsed: %s | price=₹%s | rating=%s",
                (data.get("product_name") or "?")[:60],
                data.get("selling_price") or "N/A",
                data.get("rating") or "N/A",
            )
        except Exception as exc:
            logger.exception("Parse error for %s: %s", url, exc)
            results.append({"url": url, "error": str(exc)})

        time.sleep(1.5)  # politeness delay

    # Save results
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("=" * 60)
    logger.info("Done! %d records saved to %s", len(results), OUTPUT_FILE)
    ok = sum(1 for r in results if "product_name" in r and r["product_name"])
    logger.info("Successfully parsed: %d / %d", ok, len(results))
    logger.info("=" * 60)

    # Print summary table
    print("\n── Amazon Crawl Results ─────────────────────────────────────")
    print(f"{'#':<4} {'ASIN':<12} {'Price':>8}  {'Disc':>5}  Product Name")
    print("-" * 80)
    for i, r in enumerate(results, 1):
        if "error" in r and "product_name" not in r:
            print(f"{i:<4} {'ERROR':<12} {'':>8}  {'':>5}  {r['url'][-60:]}")
        else:
            name = (r.get("product_name") or "")[:45]
            price = f"₹{r.get('selling_price')}" if r.get("selling_price") else "N/A"
            disc = f"{r.get('discount_percentage')}%" if r.get("discount_percentage") else "-"
            asin = r.get("asin") or ""
            print(f"{i:<4} {asin:<12} {price:>8}  {disc:>5}  {name}")
    print("-" * 80)
    return results


if __name__ == "__main__":
    main()
