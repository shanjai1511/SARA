"""
SARA — Storage abstraction for raw HTML and parsed records.

Backends:
  LocalStorage   — saves to local filesystem (dev / single-node)
  S3Storage      — saves to AWS S3 / S3-compatible (production)

Both share the same interface; workers import `get_storage()` which returns
the appropriate backend based on config.

Key scheme (content-addressed):
  {project}/{domain}/{YYYY-MM-DD}/{md5_of_url}.html.gz

Usage:
    from core.storage import get_storage
    store = get_storage()
    key = store.put_html(url, html_text)
    html = store.get_html(key)
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_key(url: str) -> str:
    """MD5 of URL → hex string used as filename."""
    return hashlib.md5(url.encode()).hexdigest()


def _s3_key(url: str, project: str) -> str:
    """S3 object key: {project}/{domain}/{date}/{md5}.html.gz"""
    domain = urlparse(url).netloc.removeprefix("www.")
    today = date.today().isoformat()
    return f"{project}/{domain}/{today}/{_url_key(url)}.html.gz"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseStorage(ABC):
    @abstractmethod
    def put_html(self, url: str, html: str, project: str = "default") -> str:
        """Store HTML; return opaque key."""

    @abstractmethod
    def get_html(self, key: str) -> str:
        """Retrieve HTML by key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the key exists in the store."""


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------

class LocalStorage(BaseStorage):
    """
    Stores files under base_dir/{project}/{domain}/{date}/{md5}.html.gz

    Thread-safe: each write is atomic (write to .tmp then rename).
    """

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def _path(self, key: str) -> Path:
        # key is already the relative path from base_dir
        return self.base_dir / key

    def put_html(self, url: str, html: str, project: str = "default") -> str:
        key = _s3_key(url, project)          # reuse same naming scheme
        dest = self.base_dir / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        compressed = gzip.compress(html.encode("utf-8", errors="replace"))
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(compressed)
        tmp.replace(dest)
        logger.debug("LocalStorage: saved %s → %s", url[:60], dest)
        return key

    def get_html(self, key: str) -> str:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"HTML not found: {key}")
        return gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


# ---------------------------------------------------------------------------
# S3 backend (async-capable via boto3 / aiobotocore)
# ---------------------------------------------------------------------------

class S3Storage(BaseStorage):
    """
    Stores gzip-compressed HTML in S3 or any S3-compatible store (GCS, MinIO).

    Requires: boto3
    Config via env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
                         AWS_DEFAULT_REGION, SARA_S3_BUCKET
    """

    def __init__(self, bucket: str, prefix: str = "raw"):
        self.bucket = bucket
        self.prefix = prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3  # type: ignore
            self._client = boto3.client("s3")
        return self._client

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}/{key}"

    def put_html(self, url: str, html: str, project: str = "default") -> str:
        key = _s3_key(url, project)
        full_key = self._full_key(key)
        compressed = gzip.compress(html.encode("utf-8", errors="replace"))
        self._get_client().put_object(
            Bucket=self.bucket,
            Key=full_key,
            Body=compressed,
            ContentType="text/html",
            ContentEncoding="gzip",
            Metadata={"source-url": url[:1024]},
        )
        logger.debug("S3Storage: saved %s → s3://%s/%s", url[:60], self.bucket, full_key)
        return key

    def get_html(self, key: str) -> str:
        full_key = self._full_key(key)
        obj = self._get_client().get_object(Bucket=self.bucket, Key=full_key)
        return gzip.decompress(obj["Body"].read()).decode("utf-8", errors="replace")

    def exists(self, key: str) -> bool:
        import botocore.exceptions  # type: ignore
        try:
            self._get_client().head_object(
                Bucket=self.bucket, Key=self._full_key(key)
            )
            return True
        except botocore.exceptions.ClientError:
            return False

    # ── Async wrappers (for use in async workers) ──────────────────────────

    async def aput_html(self, url: str, html: str, project: str = "default") -> str:
        """Run blocking S3 upload in thread executor (avoids blocking event loop)."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.put_html, url, html, project)

    async def aget_html(self, key: str) -> str:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_html, key)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage(base_dir: str | Path | None = None) -> BaseStorage:
    """
    Return the configured storage backend.
    - If SARA_S3_BUCKET is set → S3Storage
    - Otherwise → LocalStorage under base_dir or ./scrape_output/raw_html
    """
    bucket = os.environ.get("SARA_S3_BUCKET", "").strip()
    if bucket:
        prefix = os.environ.get("SARA_S3_PREFIX", "raw")
        logger.info("Storage backend: S3 (bucket=%s, prefix=%s)", bucket, prefix)
        return S3Storage(bucket=bucket, prefix=prefix)

    if base_dir is None:
        base_dir = Path(os.environ.get("SARA_BASE_DIR", ".")) / "scrape_output" / "raw_html"
    logger.info("Storage backend: Local (%s)", base_dir)
    return LocalStorage(base_dir=base_dir)
