from sdf_module.url_parser import *
import json
import logging
import threading

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Ajio.com Product Parser
#
# Extraction priority per field:
#   1. Ajio product detail API  GET /api/p/<code>?fields=SITE&reqType=dnld
#      — most reliable, richest data, returns JSON with everything
#   2. schema.org ld+json embedded in the SSR HTML
#      — SEO data, good fallback for price/brand/name
#   3. og:* meta tags from SSR HTML
#      — safe last resort for name and image
#
# Performance:
#   The API is fetched ONCE per product and cached in a thread-local dict
#   so all field methods share a single HTTP request.
#
# Blocking bypass:
#   Ajio uses Akamai Bot Manager.  The API call in _api_data() goes through
#   sdfFetch.get_page_content_hash() which auto-escalates to the Unblock
#   Service on 403/429 (configured via SARA_UNBLOCK_URL in .env).
# ──────────────────────────────────────────────────────────────────────────────

_PRODUCT_API = "https://www.ajio.com/api/p/{code}?fields=SITE&reqType=dnld"
_API_HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.ajio.com/",
    "sec-fetch-dest":  "empty",
    "sec-fetch-mode":  "cors",
    "sec-fetch-site":  "same-origin",
}

# Thread-local cache: one dict per parser thread so concurrent workers
# don't share state.  Cleared automatically when the thread exits.
_cache_local = threading.local()


def _get_cache() -> dict:
    if not hasattr(_cache_local, "data"):
        _cache_local.data = {}
    return _cache_local.data


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _product_url(inhash: str) -> str:
    """Strip the rank suffix: 'https://ajio.com/p/X|{"rank":1}' → URL."""
    return inhash.split("|", 1)[0] if isinstance(inhash, str) and "|" in inhash else str(inhash)


def _product_code(url: str) -> str | None:
    """
    Extract the product code from an Ajio product URL.
    Examples:
      /denim-jeans-slim-fit/p/441218669_10  →  441218669_10
      /womens-kurta/p/469258200_NVY         →  469258200_NVY
    """
    parts = url.rstrip("/").split("/")
    try:
        idx = parts.index("p")
        return parts[idx + 1] if idx + 1 < len(parts) else None
    except ValueError:
        return None


def _api_data(inhash: str) -> dict:
    """
    Fetch and cache the Ajio product detail API for this inhash.
    Returns the full JSON dict, or {} on failure.
    """
    url   = _product_url(inhash)
    cache = _get_cache()

    if url in cache:
        return cache[url]

    code = _product_code(url)
    if not code:
        cache[url] = {}
        return {}

    api_url = _PRODUCT_API.format(code=code)
    try:
        result = sdfFetch.get_page_content_hash(
            api_url,
            proxy="webshare_proxy",
            extended_header=_API_HEADERS,
            max_retries=2,
            timeout=20,
        )
        if result.get("status_code") == 200 and result.get("page_doc", "").strip():
            data = json.loads(result["page_doc"])
            cache[url] = data
            return data
    except Exception as exc:
        logger.debug("Ajio API fetch failed for %s: %s", api_url, exc)

    cache[url] = {}
    return {}


def _ld_json(page_doc) -> list[dict]:
    """Yield all schema.org objects from <script type='application/ld+json'>."""
    scripts = page_doc.xpath("//script[@type='application/ld+json']/text()")
    for raw in (scripts or []):
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item


def _ld_product(page_doc) -> dict:
    """Return the first schema.org Product object from ld+json, or {}."""
    for obj in _ld_json(page_doc):
        if obj.get("@type") in ("Product", "product"):
            return obj
    return {}


def _meta(page_doc, property_name: str) -> str | None:
    """Return the content of an og: or standard meta tag."""
    vals = page_doc.xpath(
        f"//meta[@property='{property_name}']/@content"
        f" | //meta[@name='{property_name}']/@content"
    )
    for v in vals:
        if v and v.strip():
            return v.strip()
    return None


def _clean_price(raw) -> int | None:
    """Parse a price value (string or number) to int rupees."""
    try:
        return int(float(str(raw))) or None
    except Exception:
        return None


# ── Parser class ───────────────────────────────────────────────────────────────

class AjioComCommerceCrawl():

    # ── Meta / identity ────────────────────────────────────────────────────────

    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        return datetime.now().strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return _product_url(inhash)

    @staticmethod
    def get_product_id(page_doc, inhash):
        """Ajio product code (e.g. 441218669_10)."""
        return _product_code(_product_url(inhash))

    # ── Name / brand ───────────────────────────────────────────────────────────

    @staticmethod
    def get_product_name(page_doc, inhash):
        # 1. API (most reliable)
        data = _api_data(inhash)
        if data.get("name"):
            return str(data["name"]).strip()

        # 2. ld+json
        product = _ld_product(page_doc)
        if product.get("name"):
            return str(product["name"]).strip()

        # 3. og:title
        return _meta(page_doc, "og:title")

    @staticmethod
    def get_brand(page_doc, inhash):
        # 1. API
        data = _api_data(inhash)
        brand = (
            data.get("fnlColorVariantData", {}).get("brandName")
            or data.get("brandName")
        )
        if brand:
            return str(brand).strip()

        # 2. ld+json
        product = _ld_product(page_doc)
        b = product.get("brand", {})
        if isinstance(b, dict) and b.get("name"):
            return str(b["name"]).strip()
        if isinstance(b, str) and b:
            return b.strip()

        # 3. HTML
        elems = page_doc.xpath(
            "//a[contains(@class,'brand-name')]/text()"
            " | //span[contains(@class,'brand')]/text()"
        )
        return elems[0].strip() if elems else None

    # ── Pricing ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_list_price(page_doc, inhash):
        """MRP / original price before discount."""
        # 1. API: wasPriceData is the original MRP
        data = _api_data(inhash)
        val  = data.get("wasPriceData", {}).get("value")
        if val:
            return _clean_price(val)

        # 2. ld+json offers (highPrice = MRP in some schemas)
        product = _ld_product(page_doc)
        offers  = product.get("offers", {})
        if isinstance(offers, dict):
            high = offers.get("highPrice") or offers.get("price")
            if high:
                return _clean_price(high)

        # 3. HTML MRP class
        elems = page_doc.xpath(
            "//span[contains(@class,'prod-cp')]/text()"
            " | //span[contains(@class,'prod-mrp')]/text()"
        )
        if elems:
            return _clean_price(re.sub(r"\D", "", elems[0]))

        return None

    @staticmethod
    def get_selling_price(page_doc, inhash):
        """Current selling / discounted price."""
        # 1. API: price = selling price
        data = _api_data(inhash)
        val  = data.get("price", {}).get("value")
        if val:
            p = _clean_price(val)
            if p:
                return p

        # 2. HTML selling price class
        elems = page_doc.xpath(
            "//span[contains(@class,'prod-sp')]/text()"
            " | //span[contains(@class,'prod-selling-price')]/text()"
        )
        if elems:
            p = _clean_price(re.sub(r"\D", "", elems[0]))
            if p:
                return p

        # 3. ld+json offers lowPrice / price
        product = _ld_product(page_doc)
        offers  = product.get("offers", {})
        if isinstance(offers, dict):
            low = offers.get("lowPrice") or offers.get("price")
            if low:
                return _clean_price(low)

        return AjioComCommerceCrawl.get_list_price(page_doc, inhash)

    @staticmethod
    def get_discount_percentage(page_doc, inhash):
        """Calculated: round((MRP - selling) / MRP * 100)."""
        data = _api_data(inhash)

        # API returns discountData.value directly as percentage
        disc = data.get("discountData", {}).get("value")
        if disc is not None:
            try:
                return round(float(disc))
            except Exception:
                pass

        mrp  = AjioComCommerceCrawl.get_list_price(page_doc, inhash)
        sell = AjioComCommerceCrawl.get_selling_price(page_doc, inhash)
        if mrp and sell and mrp > 0 and sell < mrp:
            return round((mrp - sell) / mrp * 100)
        return 0

    # ── Classification ─────────────────────────────────────────────────────────

    @staticmethod
    def get_category(page_doc, inhash):
        """Top-level category (e.g. 'Men', 'Women', 'Kids')."""
        data = _api_data(inhash)
        cats = data.get("categories", [])
        if cats:
            # First category is usually the broadest (Men / Women / Kids)
            return cats[0].get("name") or None

        # og:section or breadcrumb
        return _meta(page_doc, "product:category") or _meta(page_doc, "og:section")

    @staticmethod
    def get_sub_category(page_doc, inhash):
        """Sub-category (e.g. 'T-Shirts & Polos', 'Kurtas')."""
        data = _api_data(inhash)
        cats = data.get("categories", [])
        if len(cats) >= 2:
            return cats[-1].get("name") or None
        return None

    @staticmethod
    def get_gender(page_doc, inhash):
        """Target gender parsed from categories or product name."""
        data = _api_data(inhash)
        cats = data.get("categories", [])
        for cat in cats:
            name = (cat.get("name") or "").lower()
            if "women" in name or "girl" in name:
                return "Women"
            if "men" in name or "boy" in name:
                return "Men"
            if "kid" in name or "child" in name:
                return "Kids"
        # Fallback: check product name
        pname = (AjioComCommerceCrawl.get_product_name(page_doc, inhash) or "").lower()
        for kw, gender in [("women", "Women"), ("men", "Men"), ("kids", "Kids"), ("girls", "Women"), ("boys", "Men")]:
            if kw in pname:
                return gender
        return None

    # ── Variants / attributes ──────────────────────────────────────────────────

    @staticmethod
    def get_color(page_doc, inhash):
        """Product colour name."""
        data = _api_data(inhash)
        # fnlColorVariantData has the selected color
        colour = (
            data.get("fnlColorVariantData", {}).get("color")
            or data.get("color")
        )
        if colour:
            return str(colour).strip()

        # ld+json color
        product = _ld_product(page_doc)
        return product.get("color") or None

    @staticmethod
    def get_available_sizes(page_doc, inhash):
        """Comma-separated list of available (in-stock) size labels."""
        data  = _api_data(inhash)
        sizes = []

        # fnlColorVariantData.variantOptions or baseOptions
        variant_data = data.get("fnlColorVariantData", {})
        for variant in variant_data.get("variantOptions", []):
            stock = variant.get("stock", {}).get("stockLevelStatus", {}).get("code", "")
            if stock != "outOfStock":
                size_label = variant.get("sizeLabel") or variant.get("value") or variant.get("size")
                if size_label:
                    sizes.append(str(size_label))

        if not sizes:
            # Fall back to baseOptions on the root object
            for opt in data.get("baseOptions", []):
                for v in opt.get("options", []):
                    if v.get("stock", {}).get("stockLevelStatus", {}).get("code", "") != "outOfStock":
                        sz = v.get("sizeLabel") or v.get("value")
                        if sz:
                            sizes.append(str(sz))

        return ", ".join(sizes) if sizes else None

    @staticmethod
    def get_sizes_count(page_doc, inhash):
        """Number of available size options."""
        sizes = AjioComCommerceCrawl.get_available_sizes(page_doc, inhash)
        if not sizes:
            return 0
        return len([s for s in sizes.split(",") if s.strip()])

    # ── Content ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_description(page_doc, inhash):
        """Product description text (cleaned, no HTML)."""
        # 1. API description field
        data = _api_data(inhash)
        desc = data.get("description") or data.get("summary") or ""
        if desc:
            # Strip any HTML tags that may be embedded
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()
            if desc:
                return desc

        # 2. ld+json
        product = _ld_product(page_doc)
        if product.get("description"):
            return str(product["description"]).strip()

        # 3. og:description / meta description
        return _meta(page_doc, "og:description") or _meta(page_doc, "description")

    @staticmethod
    def get_images(page_doc, inhash):
        """Comma-separated list of product image URLs (full resolution)."""
        data   = _api_data(inhash)
        images = []

        # API: images array — filter out thumbnails (look for PRODUCT_ZOOM or large)
        for img in data.get("images", []):
            url = img.get("url", "")
            if url:
                # Ensure absolute URL
                if url.startswith("//"):
                    url = "https:" + url
                elif not url.startswith("http"):
                    url = "https://assets.ajio.com" + url
                images.append(url)

        if not images:
            # ld+json image
            product = _ld_product(page_doc)
            img_val = product.get("image")
            if isinstance(img_val, str):
                images = [img_val]
            elif isinstance(img_val, list):
                images = [i for i in img_val if isinstance(i, str)]

        if not images:
            og_img = _meta(page_doc, "og:image")
            if og_img:
                images = [og_img]

        return ", ".join(images[:8]) if images else None   # cap at 8 images

    @staticmethod
    def get_primary_image(page_doc, inhash):
        """First (main) product image URL."""
        images = AjioComCommerceCrawl.get_images(page_doc, inhash)
        if images:
            return images.split(",")[0].strip()
        return None

    # ── Ratings ────────────────────────────────────────────────────────────────

    @staticmethod
    def get_rating(page_doc, inhash):
        """Average customer rating (0.0–5.0)."""
        data = _api_data(inhash)

        # API: averageRating
        rating = data.get("averageRating")
        if rating is not None:
            try:
                return round(float(rating), 1)
            except Exception:
                pass

        # ld+json aggregateRating
        product = _ld_product(page_doc)
        agg     = product.get("aggregateRating", {})
        val     = agg.get("ratingValue") if isinstance(agg, dict) else None
        if val is not None:
            try:
                return round(float(val), 1)
            except Exception:
                pass

        return None

    @staticmethod
    def get_review_count(page_doc, inhash):
        """Total number of customer reviews."""
        data = _api_data(inhash)
        n    = data.get("numberOfReviews")
        if n is not None:
            try:
                return int(n)
            except Exception:
                pass

        # ld+json
        product = _ld_product(page_doc)
        agg     = product.get("aggregateRating", {})
        cnt     = agg.get("reviewCount") if isinstance(agg, dict) else None
        if cnt is not None:
            try:
                return int(cnt)
            except Exception:
                pass

        return None

    # ── Availability ───────────────────────────────────────────────────────────

    @staticmethod
    def get_availability(page_doc, inhash):
        """'in_stock' or 'out_of_stock'."""
        data  = _api_data(inhash)
        stock = data.get("stock", {}).get("stockLevelStatus", {}).get("code", "")
        if stock:
            return "in_stock" if stock.lower() == "instock" else "out_of_stock"

        # ld+json offers availability
        product = _ld_product(page_doc)
        avail   = (product.get("offers", {}) or {}).get("availability", "")
        if avail:
            return "in_stock" if "InStock" in avail else "out_of_stock"

        return None

    # ── Material ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_material(page_doc, inhash):
        """Fabric / material composition (e.g. '100% Cotton')."""
        data = _api_data(inhash)

        # classifications → features → name='Fabric'|'Material'
        for classification in data.get("classifications", []):
            for feature in classification.get("features", []):
                name = (feature.get("name") or "").lower()
                if "fabric" in name or "material" in name or "composition" in name:
                    values = feature.get("featureValues", [])
                    if values:
                        return values[0].get("value") or None

        # ld+json material property
        product = _ld_product(page_doc)
        return product.get("material") or None
