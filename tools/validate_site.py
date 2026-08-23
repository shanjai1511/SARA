"""
Site config validator — checks that a site's Python parser class
has a get_<field> method for every field declared in its YAML.

Usage:
    python -m tools.validate_site <project> <site>
    python -m tools.validate_site --all         # validate every configured site

Examples:
    python -m tools.validate_site commerce_crawl myntra_com
    python -m tools.validate_site media_crawl wwd_com
    python -m tools.validate_site --all
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from sdf_module.files_import import normalize_class_name


def validate(project: str, site: str) -> list[str]:
    """Return list of error strings. Empty list = valid."""
    errors: list[str] = []

    discovery_yml = ROOT / "url_discovery" / project / f"{site}_{project}.yml"
    discovery_py  = ROOT / "url_discovery" / project / f"{site}_{project}.py"
    parser_yml    = ROOT / "url_data_parser" / project / f"{site}_{project}.yml"
    parser_py     = ROOT / "url_data_parser" / project / f"{site}_{project}.py"

    # ── Discovery checks ────────────────────────────────────────────────────
    if not discovery_yml.exists():
        errors.append(f"Missing discovery YAML: {discovery_yml}")
    if not discovery_py.exists():
        errors.append(f"Missing discovery Python: {discovery_py}")

    if discovery_yml.exists() and discovery_py.exists():
        with open(discovery_yml, encoding="utf-8") as f:
            disc_config = yaml.safe_load(f) or {}

        # Check seed URLs are set
        seeds = disc_config.get("depth0", {}).get("seed_url", [])
        if isinstance(seeds, str):
            seeds = [seeds]
        if not seeds or all(not s.strip() or "TODO" in s for s in seeds):
            errors.append("discovery YAML: depth0.seed_url not configured (still has TODO or empty)")

        # Load discovery class and check methods
        class_name = normalize_class_name(project, site)
        try:
            spec = importlib.util.spec_from_file_location(class_name, discovery_py)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            disc_class = getattr(mod, class_name)
        except Exception as e:
            errors.append(f"Discovery Python import failed: {e}")
            disc_class = None

        if disc_class:
            for depth_key, depth_val in disc_config.items():
                if not depth_key.startswith("depth"):
                    continue
                method = depth_val.get("method_name") if isinstance(depth_val, dict) else None
                if method and not callable(getattr(disc_class, method, None)):
                    errors.append(f"Discovery Python: missing method '{method}' (required by {depth_key})")

    # ── Parser checks ────────────────────────────────────────────────────────
    if not parser_yml.exists():
        errors.append(f"Missing parser YAML: {parser_yml}")
    if not parser_py.exists():
        errors.append(f"Missing parser Python: {parser_py}")

    if parser_yml.exists() and parser_py.exists():
        with open(parser_yml, encoding="utf-8") as f:
            parser_config = yaml.safe_load(f) or {}

        fields = parser_config.get("fields", {})
        if not fields:
            errors.append("Parser YAML: no fields defined")

        # Load parser class
        class_name = normalize_class_name(project, site)
        try:
            spec = importlib.util.spec_from_file_location(class_name, parser_py)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            parser_class = getattr(mod, class_name)
        except Exception as e:
            errors.append(f"Parser Python import failed: {e}")
            parser_class = None

        if parser_class and fields:
            for field in fields:
                method = f"get_{field}"
                if not callable(getattr(parser_class, method, None)):
                    errors.append(f"Parser Python: missing method '{method}' (field '{field}' in YAML)")

    return errors


def validate_all() -> dict[str, list[str]]:
    """Validate every site found in url_discovery/."""
    results: dict[str, list[str]] = {}
    disc_root = ROOT / "url_discovery"
    for project_dir in sorted(disc_root.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name
        for yml in sorted(project_dir.glob("*.yml")):
            site = yml.stem.replace(f"_{project}", "")
            key = f"{project}/{site}"
            results[key] = validate(project, site)
    return results


def main():
    parser = argparse.ArgumentParser(description="Validate site discovery + parser configuration.")
    parser.add_argument("project", nargs="?", help="Project name")
    parser.add_argument("site",    nargs="?", help="Site name")
    parser.add_argument("--all",   action="store_true", help="Validate all configured sites")
    args = parser.parse_args()

    if args.all:
        results = validate_all()
        ok = sum(1 for e in results.values() if not e)
        fail = sum(1 for e in results.values() if e)
        for key, errors in results.items():
            status = "OK" if not errors else "FAIL"
            print(f"[{status}] {key}")
            for e in errors:
                print(f"       ✗ {e}")
        print(f"\n{ok} OK, {fail} FAIL out of {len(results)} sites")
        if fail:
            sys.exit(1)
    else:
        if not args.project or not args.site:
            parser.error("Provide project and site, or use --all")
        errors = validate(args.project, args.site)
        if not errors:
            print(f"[OK] {args.project}/{args.site} — all checks passed")
        else:
            print(f"[FAIL] {args.project}/{args.site}")
            for e in errors:
                print(f"  ✗ {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
