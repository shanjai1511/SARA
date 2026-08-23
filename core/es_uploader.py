"""
Elasticsearch uploader for SARA parsed output.

Two indices only:
    sara-commerce-crawl   — all commerce sites
    sara-media-crawl      — all media sites

Each document gets a `site_name` field added automatically.
`crawl_timestamp` is mapped to ES `@timestamp` for time-based views in Kibana.

Configuration (via .env):
    ELASTICSEARCH_URL      Full ES URL, e.g. https://localhost:9200
    ELASTICSEARCH_API_KEY  Base64 API key (preferred) — OR use user/pass below
    ELASTICSEARCH_USER     ES username (if not using API key)
    ELASTICSEARCH_PASSWORD ES password (if not using API key)

If ELASTICSEARCH_URL is not set, upload is silently skipped.
"""
from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime
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


def _index_name(project_name: str) -> str:
    """Two indices: sara-commerce-crawl and sara-media-crawl."""
    return f"sara-{project_name}".lower().replace("_", "-")


def _ensure_index(client, index: str) -> None:
    if client.indices.exists(index=index):
        return
    client.indices.create(
        index=index,
        body={
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "@timestamp": {"type": "date"},
                    "site_name": {"type": "keyword"},
                    "crawl_timestamp": {"type": "keyword"},
                },
            },
        },
    )
    log.info("Created ES index: %s", index)


_TS_FORMATS = [
    "%b %d, %Y @ %H:%M:%S.%f",   # Mar 11, 2026 @ 23:26:23.030
    "%Y-%m-%dT%H:%M:%S.%f",       # ISO with ms
    "%Y-%m-%dT%H:%M:%S",          # ISO without ms
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
]


def _to_iso(ts: str) -> str | None:
    """Convert any crawl_timestamp format to ISO 8601 for ES."""
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(ts.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except ValueError:
            continue
    return None


def _iter_bulk_actions(csv_path: Path, index: str, site_name: str) -> Iterator[dict]:
    """Stream bulk-action dicts from CSV — never loads the full file into memory."""
    for doc in _read_csv(csv_path, site_name):
        yield {"_index": index, "_source": doc}


def _chunked(it: Iterator, n: int) -> Iterator[list]:
    """Yield successive n-sized chunks from iterator without buffering the whole stream."""
    chunk: list = []
    for item in it:
        chunk.append(item)
        if len(chunk) >= n:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _read_csv(csv_path: Path, site_name: str) -> Iterator[dict]:
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = {k: v for k, v in row.items() if v not in (None, "")}
            # Add site_name for filtering in Kibana
            doc["site_name"] = site_name
            # Map crawl_timestamp → @timestamp (ISO 8601) for Kibana time filter
            raw_ts = doc.get("crawl_timestamp", "")
            if raw_ts:
                iso = _to_iso(raw_ts)
                if iso:
                    doc["@timestamp"] = iso
            yield doc


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
        index = _index_name(project_name)
        _ensure_index(client, index)

        # Stream through CSV in BULK_CHUNK-sized windows — O(BULK_CHUNK) memory,
        # not O(total_records). Safe for CSVs with millions of rows.
        action_stream = _iter_bulk_actions(csv_path, index, site_name)
        chunk_number  = 0
        first_chunk   = True

        total = 0
        _ES_BULK_RETRIES = 3
        for chunk in _chunked(action_stream, BULK_CHUNK):
            if first_chunk and not chunk:
                log.info("No records to upload for schedule_key=%s", schedule_key)
                return 0
            first_chunk  = False
            chunk_number += 1
            i             = (chunk_number - 1) * BULK_CHUNK  # for error messages
            chunk_ok = False
            for attempt in range(_ES_BULK_RETRIES):
                try:
                    success, errors = bulk(client, chunk, raise_on_error=False)
                    total += success
                    if errors:
                        log.warning(
                            "ES bulk chunk errors (%d/%d docs) attempt %d: %s",
                            len(errors), len(chunk), attempt + 1, errors[:3],
                        )
                    chunk_ok = True
                    break
                except Exception as exc:
                    wait = 2 ** attempt
                    log.warning(
                        "ES bulk chunk failed (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1, _ES_BULK_RETRIES, exc, wait,
                    )
                    time.sleep(wait)

            if not chunk_ok:
                log.error(
                    "ES bulk chunk permanently failed after %d attempts "
                    "(index=%s, schedule=%s, chunk_start=%d)",
                    _ES_BULK_RETRIES, index, schedule_key, i,
                )
                try:
                    from core.alerting import send_failure_alert
                    send_failure_alert(
                        project_name="es_uploader",
                        site_name=site_name,
                        schedule_id=schedule_key,
                        stage="es_bulk",
                        error_detail=f"chunk starting at doc {i} failed after {_ES_BULK_RETRIES} attempts",
                    )
                except Exception:
                    pass  # alerting failure must never crash the uploader

        log.info(
            "ES upload complete | index=%s site=%s schedule=%s docs=%d",
            index, site_name, schedule_key, total,
        )
        return total

    except ImportError:
        log.warning("elasticsearch package not installed — skipping ES upload.")
        return 0
    except Exception:
        log.exception("ES upload failed for schedule_key=%s", schedule_key)
        try:
            from core.alerting import send_failure_alert
            send_failure_alert(
                project_name="es_uploader",
                site_name=site_name,
                schedule_id=schedule_key,
                stage="es_upload",
                error_detail="Exception during upload — see pipeline.log",
            )
        except Exception:
            pass
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
        # Path: parser_output/{project}/{site}_{project}_{schedule}/{site}_{project}.csv
        try:
            schedule_dir = csv_path.parent.name          # e.g. myntra_com_commerce_crawl_20250410
            project_name = csv_path.parent.parent.name   # e.g. commerce_crawl
            # site_name: strip _{project}_{schedule} suffix
            site_name = schedule_dir.replace(f"_{project_name}_", "_").rsplit("_", 1)[0]
            schedule_key = schedule_dir.rsplit("_", 1)[-1]
        except (IndexError, ValueError):
            log.warning("Could not parse path structure for: %s", csv_path)
            continue

        count = upload_csv(csv_path, project_name, site_name, schedule_key)
        total += count

    log.info("Backfill complete — total docs uploaded: %d", total)
    return total
