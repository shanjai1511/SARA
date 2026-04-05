"""
Elasticsearch uploader for SARA parsed output.

Reads CSV files produced by url_parser.py and bulk-indexes them into ES.
Index naming convention: sara-{project_name}-{site_name}

Configuration (via .env):
    ELASTICSEARCH_URL      Full ES URL, e.g. https://my-cluster.es.io:9243
    ELASTICSEARCH_API_KEY  Base64 API key (preferred) — OR use user/pass below
    ELASTICSEARCH_USER     ES username (if not using API key)
    ELASTICSEARCH_PASSWORD ES password (if not using API key)

If ELASTICSEARCH_URL is not set, upload is silently skipped.
"""
from __future__ import annotations

import csv
import logging
import os
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

BULK_CHUNK = 500  # documents per bulk request


def _es_enabled() -> bool:
    return bool(os.environ.get("ELASTICSEARCH_URL", "").strip())


def _get_client():
    """Return an Elasticsearch client or raise if not configured."""
    from elasticsearch import Elasticsearch

    url = os.environ["ELASTICSEARCH_URL"].strip()
    api_key = os.environ.get("ELASTICSEARCH_API_KEY", "").strip()
    user = os.environ.get("ELASTICSEARCH_USER", "").strip()
    password = os.environ.get("ELASTICSEARCH_PASSWORD", "").strip()

    # Disable cert verification for self-hosted ES with self-signed certs
    ssl_local = url.startswith("https://localhost") or url.startswith("https://127.")

    if api_key:
        return Elasticsearch(url, api_key=api_key, verify_certs=not ssl_local, ssl_show_warn=False)
    elif user and password:
        return Elasticsearch(url, basic_auth=(user, password), verify_certs=not ssl_local, ssl_show_warn=False)
    else:
        return Elasticsearch(url, verify_certs=not ssl_local, ssl_show_warn=False)


def _index_name(project_name: str, site_name: str) -> str:
    return f"sara-{project_name}-{site_name}".lower().replace("_", "-")


def _read_csv(csv_path: Path) -> Iterator[dict]:
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Drop empty-string values so ES mapping stays clean
            yield {k: v for k, v in row.items() if v not in (None, "")}


def _bulk_actions(docs: Iterator[dict], index: str) -> Iterator[dict]:
    for doc in docs:
        yield {"_index": index, "_source": doc}


def upload_csv(
    csv_path: Path,
    project_name: str,
    site_name: str,
    schedule_key: str,
) -> int:
    """
    Upload a parser output CSV to Elasticsearch.

    Returns the number of documents indexed (0 if ES is not configured).
    """
    if not _es_enabled():
        log.debug("ELASTICSEARCH_URL not set — skipping ES upload.")
        return 0

    if not csv_path.exists():
        log.warning("CSV not found, skipping ES upload: %s", csv_path)
        return 0

    try:
        from elasticsearch.helpers import bulk

        client = _get_client()
        index = _index_name(project_name, site_name)

        # Ensure index exists with basic dynamic mapping
        if not client.indices.exists(index=index):
            client.indices.create(
                index=index,
                body={
                    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                    "mappings": {"dynamic": True},
                },
            )
            log.info("Created ES index: %s", index)

        docs = _read_csv(csv_path)
        actions = list(_bulk_actions(docs, index))

        if not actions:
            log.info("No records to upload for schedule_key=%s", schedule_key)
            return 0

        # Bulk in chunks to avoid request-size limits
        total = 0
        for i in range(0, len(actions), BULK_CHUNK):
            chunk = actions[i: i + BULK_CHUNK]
            success, errors = bulk(client, chunk, raise_on_error=False)
            total += success
            if errors:
                log.warning("ES bulk errors (%d): %s", len(errors), errors[:3])

        log.info(
            "ES upload complete | index=%s schedule=%s docs=%d",
            index, schedule_key, total,
        )
        return total

    except ImportError:
        log.warning("elasticsearch package not installed — skipping ES upload.")
        return 0
    except Exception:
        log.exception("ES upload failed for schedule_key=%s", schedule_key)
        return 0


def upload_all_existing(base_dir: Path) -> int:
    """
    Walk scrape_output/parser_output and upload all CSV files found.
    Useful for backfilling existing data into ES.
    """
    parser_output = base_dir / "scrape_output" / "parser_output"
    if not parser_output.exists():
        log.warning("parser_output dir not found: %s", parser_output)
        return 0

    total = 0
    for csv_path in parser_output.rglob("*.csv"):
        # Path structure: parser_output/{project}/{site}_{project}_{schedule}/{site}_{project}.csv
        parts = csv_path.parts
        try:
            schedule_dir = csv_path.parent.name          # e.g. myntra_com_commerce_crawl_20250410
            project_name = csv_path.parent.parent.name   # e.g. commerce_crawl
            # derive site_name from schedule_dir prefix (strip _{project}_{schedule})
            site_name = schedule_dir.replace(f"_{project_name}_", "_").rsplit("_", 1)[0]
            schedule_key = schedule_dir.rsplit("_", 1)[-1]
        except (IndexError, ValueError):
            log.warning("Could not parse path structure for: %s", csv_path)
            continue

        count = upload_csv(csv_path, project_name, site_name, schedule_key)
        total += count

    log.info("Backfill complete — total docs uploaded: %d", total)
    return total
