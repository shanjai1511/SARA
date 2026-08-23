"""
run_all_sites_direct.py — batch runner: discover -> fetch -> parse for every
configured site, queueless (see run_direct_crawl.py), across both projects.

Full-depth, uncapped, per site — this is a long-running, network-bound batch
job across ~174 real external sites. It is resumable: a site is skipped on
restart if its output CSV for SCHEDULE_ID already exists.

Usage:
    python run_all_sites_direct.py [--project media_crawl|commerce_crawl] [--concurrency N] [--schedule-id ID]

    Without --schedule-id, defaults to "direct" + today's date — which means
    resuming on a later calendar day silently starts a NEW schedule (breaking
    resumability against a prior day's run) unless --schedule-id is passed
    explicitly to match it.

Progress:
    One "PROGRESS ..." line per completed site on stdout.
    Running summary written to reports/direct_crawl_summary.json after each site.
    Final "BATCH_DONE ..." line with aggregate totals.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from dotenv import load_dotenv
load_dotenv()

from run_direct_crawl import run as run_site
from sdf_module.sdf_fetch import disable_proxy

BASE_DIR      = Path(__file__).resolve().parent
SCHEDULE_ID   = "direct" + time.strftime("%Y%m%d")
SUMMARY_FILE  = BASE_DIR / "reports" / "direct_crawl_summary.json"
DEFAULT_CONCURRENCY = 5   # mirrors the existing sara-worker@1..5 pool convention

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("batch")

_summary_lock = threading.Lock()


def _requires_proxy(project: str, site: str) -> bool:
    yml_path = BASE_DIR / "url_discovery" / project / f"{site}_{project}.yml"
    try:
        config = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return bool(config.get("request_params", {}).get("proxy"))


def list_sites(project_filter: str | None = None) -> list[tuple[str, str]]:
    """Every (project, site) pair configured under url_discovery/, ordered so
    proxy-independent sites run first — with a bounded worker pool, a single
    broken proxy pool shouldn't starve every unaffected site behind it."""
    pairs: list[tuple[str, str]] = []
    disc_root = BASE_DIR / "url_discovery"
    for project_dir in sorted(disc_root.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name
        if project_filter and project != project_filter:
            continue
        for yml in sorted(project_dir.glob("*.yml")):
            site = yml.stem.replace(f"_{project}", "")
            pairs.append((project, site))
    return sorted(pairs, key=lambda ps: _requires_proxy(*ps))


def _csv_path(project: str, site: str) -> Path:
    return (
        BASE_DIR / "scrape_output" / "parser_output" / project
        / f"{site}_{project}_{SCHEDULE_ID}" / f"{site}_{project}.csv"
    )


def _load_summary() -> dict:
    if SUMMARY_FILE.exists():
        try:
            return json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"schedule_id": SCHEDULE_ID, "started_at": None, "results": {}}


def _save_summary(summary: dict) -> None:
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SUMMARY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(SUMMARY_FILE)


def _run_one(project: str, site: str, index: int, total: int, summary: dict) -> None:
    key = f"{project}/{site}"

    if _csv_path(project, site).exists():
        logger.info("PROGRESS [%d/%d] %s status=skipped (already done)", index, total, key)
        with _summary_lock:
            summary["results"].setdefault(key, {"status": "skipped_existing"})
            _save_summary(summary)
        return

    started = time.time()
    try:
        result = run_site(project, site, SCHEDULE_ID)
        result["duration_s"] = round(time.time() - started, 1)
        logger.info(
            "PROGRESS [%d/%d] %s status=%s discovered=%s fetched=%s failed=%s (%.0fs)",
            index, total, key, result.get("status"), result.get("discovered"),
            result.get("fetched"), result.get("failed"), result["duration_s"],
        )
    except Exception as exc:
        result = {
            "project": project, "site": site, "schedule_id": SCHEDULE_ID,
            "status": "error", "error": str(exc),
            "duration_s": round(time.time() - started, 1),
        }
        logger.error("PROGRESS [%d/%d] %s status=error error=%s", index, total, key, exc)
        logger.debug(traceback.format_exc())

    with _summary_lock:
        summary["results"][key] = result
        _save_summary(summary)


def main() -> None:
    global SCHEDULE_ID

    parser = argparse.ArgumentParser(description="Queueless batch crawl for all configured sites.")
    parser.add_argument("--project", choices=["media_crawl", "commerce_crawl"], default=None)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--schedule-id", default=None, help="Resume/target a specific schedule_id instead of today's date")
    args = parser.parse_args()

    if args.schedule_id:
        SCHEDULE_ID = args.schedule_id

    disable_proxy()   # Webshare account is out of credit — fetch direct instead
    sites = list_sites(args.project)
    total = len(sites)
    logger.info(
        "BATCH_START schedule_id=%s sites=%d concurrency=%d", SCHEDULE_ID, total, args.concurrency
    )

    summary = _load_summary()
    summary["schedule_id"] = SCHEDULE_ID
    summary.setdefault("started_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    _save_summary(summary)

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futs = [
            executor.submit(_run_one, project, site, i, total, summary)
            for i, (project, site) in enumerate(sites, 1)
        ]
        for fut in as_completed(futs):
            fut.result()   # surface any unexpected exception from _run_one itself

    statuses = [r.get("status") for r in summary["results"].values()]
    counts = {s: statuses.count(s) for s in set(statuses)}
    logger.info("BATCH_DONE schedule_id=%s sites=%d counts=%s", SCHEDULE_ID, total, counts)


if __name__ == "__main__":
    main()
