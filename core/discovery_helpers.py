"""
Shared pagination helpers for discovery scripts.

Import in any site discovery file:
    from core.discovery_helpers import wordpress_pages, querystring_pages, shopify_pages

These replace the boilerplate loop that every site currently reimplements.
"""
from __future__ import annotations

from urllib.parse import urlencode, urljoin, urlparse, parse_qs, urlencode, urlunparse


def wordpress_pages(seed_url: str, count: int = 10) -> list[str]:
    """
    Return paginated URLs for a WordPress category/tag/archive page.
    Page 1 is the seed (already crawled); returns pages 2..count+1.

    Example:
        seed = "https://wwd.com/fashion-news/"
        → ["https://wwd.com/fashion-news/page/2/",
           "https://wwd.com/fashion-news/page/3/", ...]
    """
    base = seed_url.rstrip("/")
    return [f"{base}/page/{i}/" for i in range(2, count + 2)]


def querystring_pages(seed_url: str, param: str = "page", start: int = 1, count: int = 10) -> list[str]:
    """
    Return paginated URLs using a query-string parameter.

    Example (start=1):
        seed = "https://www.vogue.in/fashion/"
        → ["https://www.vogue.in/fashion/?page=1",
           "https://www.vogue.in/fashion/?page=2", ...]

    Example (start=2, to skip page 1 which is the seed):
        → ["https://www.vogue.in/fashion/?page=2", ...]
    """
    parsed = urlparse(seed_url)
    results = []
    for i in range(start, start + count):
        qs = parse_qs(parsed.query)
        qs[param] = [str(i)]
        new_query = urlencode({k: v[0] for k, v in qs.items()})
        new = parsed._replace(query=new_query)
        results.append(urlunparse(new))
    return results


def shopify_pages(seed_url: str, count: int = 10) -> list[str]:
    """
    Return paginated URLs for a Shopify collection page.
    Shopify uses ?page=N.

    Example:
        seed = "https://www.example.com/collections/women"
        → ["https://www.example.com/collections/women?page=1", ...]
    """
    return querystring_pages(seed_url, param="page", start=1, count=count)


def path_number_pages(seed_url: str, count: int = 10) -> list[str]:
    """
    Return paginated URLs where the page number is appended as a path segment.
    Used by sites like Fibre2Fashion: /industry-article/fashion/1/

    Example:
        seed = "https://www.fibre2fashion.com/industry-article/fashion/"
        → ["https://www.fibre2fashion.com/industry-article/fashion/1/",
           "https://www.fibre2fashion.com/industry-article/fashion/2/", ...]
    """
    base = seed_url.rstrip("/")
    return [f"{base}/{i}/" for i in range(1, count + 1)]
