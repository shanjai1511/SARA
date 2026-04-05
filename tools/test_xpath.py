"""
XPath / CSS selector tester — fetch a URL and test extraction expressions.

Usage:
    python -m tools.test_xpath <url> <xpath_or_css> [<xpath2> ...]

Examples:
    python -m tools.test_xpath https://wwd.com/fashion-news/some-article/ "//h1/text()"
    python -m tools.test_xpath https://www.myntra.com/product/123 "//h1[@class='pdp-title']/text()" "//span[@class='pdp-price']/text()"
    python -m tools.test_xpath https://example.com/article "//meta[@property='og:title']/@content"

Tip: wrap XPath in single quotes on the shell to avoid issues with double quotes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lxml import html, etree
from sdf_module.sdf_fetch import sdfFetch


def _fetch(url: str) -> str | None:
    print(f"Fetching: {url}")
    result = sdfFetch.get_page_content_hash(url)
    if result.get("status_code") != 200:
        print(f"ERROR: HTTP {result.get('status_code')} — could not fetch page")
        return None
    return result["page_doc"]


def _test_xpath(tree, expr: str) -> None:
    print(f"\nXPath: {expr}")
    try:
        results = tree.xpath(expr)
        if not results:
            print("  → No results")
        else:
            print(f"  → {len(results)} result(s):")
            for i, r in enumerate(results[:10]):
                if isinstance(r, str):
                    val = r.strip()
                elif hasattr(r, "text_content"):
                    val = r.text_content().strip()
                else:
                    val = str(r).strip()
                print(f"  [{i}] {val[:200]}")
            if len(results) > 10:
                print(f"  ... and {len(results)-10} more")
    except etree.XPathError as e:
        print(f"  ERROR: invalid XPath — {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch a page and test XPath expressions against it."
    )
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("expressions", nargs="+", help="XPath expression(s) to test")
    args = parser.parse_args()

    page = _fetch(args.url)
    if not page:
        sys.exit(1)

    tree = html.fromstring(page)
    print(f"\nPage fetched ({len(page):,} bytes)\n{'─'*50}")

    for expr in args.expressions:
        _test_xpath(tree, expr)

    print(f"\n{'─'*50}")
    print("Done. Adjust XPath expressions and re-run to iterate.")


if __name__ == "__main__":
    main()
