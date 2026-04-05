"""
Discovery dry-run tool — test URL discovery for a site without running the pipeline.

Usage:
    python -m tools.test_discovery <project> <site> [--depth N] [--limit N]

Examples:
    python -m tools.test_discovery media_crawl wwd_com
    python -m tools.test_discovery commerce_crawl myntra_com --depth 0
    python -m tools.test_discovery media_crawl drapers_com --limit 5

Outputs:
    - Pagination URLs generated for each seed (depth 0)
    - Article/product URLs found by discovery (depth 1)
    - Summary counts
    - Any errors encountered

Does NOT push to RabbitMQ — purely a preview/validation tool.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

# Make sure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from sdf_module.sdf_fetch import sdfFetch
from sdf_module.files_import import normalize_class_name
from lxml import html


def _load_site(project: str, site: str):
    yml_path = ROOT / "url_discovery" / project / f"{site}_{project}.yml"
    py_path  = ROOT / "url_discovery" / project / f"{site}_{project}.py"

    if not yml_path.exists():
        print(f"ERROR: YAML not found: {yml_path}")
        sys.exit(1)
    if not py_path.exists():
        print(f"ERROR: Python not found: {py_path}")
        sys.exit(1)

    with open(yml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    class_name = normalize_class_name(project, site)
    spec = importlib.util.spec_from_file_location(class_name, py_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    instance = getattr(mod, class_name)()
    return config, instance


def run(project: str, site: str, max_depth: int = 1, limit: int = 10) -> None:
    print(f"\n{'='*60}")
    print(f"  Discovery dry-run: {project} / {site}")
    print(f"{'='*60}\n")

    config, instance = _load_site(project, site)

    depth0 = config.get("depth0", {})
    seed_urls = depth0.get("seed_url", [])
    if isinstance(seed_urls, str):
        seed_urls = [seed_urls]

    print(f"[depth0] {len(seed_urls)} seed URL(s):")
    for u in seed_urls:
        print(f"  {u}")

    # ── Depth 0: pagination ─────────────────────────────────────────────────
    d0_method = depth0.get("method_name")
    if not d0_method or max_depth < 0:
        return

    pagination_method = getattr(instance, d0_method, None)
    if not callable(pagination_method):
        print(f"ERROR: method '{d0_method}' not found on {instance.__class__.__name__}")
        return

    all_pagination: list[str] = []
    for seed in seed_urls:
        try:
            pages = pagination_method(seed, config, 0) or []
            all_pagination.extend(pages)
        except Exception as e:
            print(f"  ERROR in {d0_method}({seed}): {e}")

    print(f"\n[depth0] → {len(all_pagination)} pagination URL(s) generated:")
    for u in all_pagination[:5]:
        print(f"  {u}")
    if len(all_pagination) > 5:
        print(f"  ... and {len(all_pagination)-5} more")

    if max_depth < 1:
        return

    # ── Depth 1: product/article URLs ───────────────────────────────────────
    depth1 = config.get("depth1", {})
    d1_method = depth1.get("method_name")
    if not d1_method:
        return

    product_method = getattr(instance, d1_method, None)
    if not callable(product_method):
        print(f"ERROR: method '{d1_method}' not found")
        return

    # Test against first few pagination URLs
    test_urls = (all_pagination or seed_urls)[:limit]
    print(f"\n[depth1] Testing '{d1_method}' against {len(test_urls)} URL(s) (limit={limit})...")

    all_products: list[str] = []
    errors = 0
    for url in test_urls:
        print(f"  Fetching: {url}")
        try:
            time.sleep(1)  # polite delay
            products = product_method(url, config, 1) or []
            all_products.extend(products)
            print(f"    → {len(products)} URL(s) found")
            for p in products[:3]:
                print(f"      {p}")
            if len(products) > 3:
                print(f"      ... and {len(products)-3} more")
        except Exception as e:
            print(f"    ERROR: {e}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Pagination URLs : {len(all_pagination)}")
    print(f"  Test URLs tried : {len(test_urls)}")
    print(f"  Article/product URLs found: {len(all_products)}")
    print(f"  Errors          : {errors}")
    if errors == len(test_urls):
        print("\n  ⚠  All attempts failed — check seed URLs, proxy config, or site blocking")
    elif len(all_products) == 0:
        print("\n  ⚠  0 URLs found — check URL filter logic in get_product_url()")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Test discovery for a site without running the pipeline.")
    parser.add_argument("project", help="Project name (e.g. media_crawl)")
    parser.add_argument("site",    help="Site name (e.g. wwd_com)")
    parser.add_argument("--depth", type=int, default=1,
                        help="Max depth level to test (0=pagination only, 1=full, default: 1)")
    parser.add_argument("--limit", type=int, default=3,
                        help="Max number of pagination pages to fetch for depth-1 testing (default: 3)")
    args = parser.parse_args()
    run(args.project, args.site, max_depth=args.depth, limit=args.limit)


if __name__ == "__main__":
    main()
