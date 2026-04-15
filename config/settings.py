"""
Centralised settings for SARA.

Loaded once at import time. Every other module reads from this object
instead of calling os.environ directly.

Usage:
    from config.settings import settings
    url = settings.CLOUDAMQP_URL

Required env vars (must be set — no hardcoded fallback):
    CLOUDAMQP_URL       Full AMQP(S) connection URL for RabbitMQ
    DASHBOARD_PASSWORD  Password to access the Streamlit dashboard
    WEBSHARE_PROXY_JSON JSON array of proxy tuples (loaded by proxy_config.py)

Optional tuning vars (safe defaults provided):
    NUM_FETCH_WORKERS                Parallel workers for URL retrieval (default: 8)
    NUM_PARSE_WORKERS                Parallel workers for HTML parsing  (default: 8)
    NUM_DISCOVERY_WORKERS            Parallel workers for URL discovery (default: 6)
    MAX_URLS                         Max URLs pulled from queue per run  (default: 500)
    FETCH_DELAY                      Seconds between discovery calls    (default: 5)
    FETCH_SLEEP_SEC                  Seconds between retriever fetches  (default: 2)
    DISCOVERY_BACKPRESSURE_THRESHOLD Max queue depth before discovery pauses (default: 50000)

SaaS / production vars (all optional — enable cloud features when set):
    REDIS_URL           Redis connection URL (enables Bloom filter + rate limiting)
    SARA_S3_BUCKET      S3 bucket for raw HTML storage (enables cloud storage)
    SARA_S3_PREFIX      S3 key prefix (default: raw)
    AWS_DEFAULT_REGION  AWS region for S3 (default: us-east-1)
    SARA_API_KEY        Bearer token for FastAPI control plane
    METRICS_PORT        Prometheus /metrics server port (default: 8000)
    CORS_ORIGINS        Comma-separated allowed origins for API CORS
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Load .env when present (development workflow).
# In production the platform injects env vars directly — load_dotenv is a no-op.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on platform-supplied env vars


def _require(key: str) -> str:
    """Return the env var value or raise a clear error if it is absent/empty."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in the value."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    """Return the env var value or default if absent."""
    return os.environ.get(key, default).strip()


def _optional_int(key: str, default: int) -> int:
    """Return the env var as an int, or *default* if the var is absent."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise EnvironmentError(
            f"Environment variable '{key}' must be an integer, got: {raw!r}"
        )


@dataclass(frozen=True)
class Settings:
    # ── Secrets (must be present; process fails loudly if missing) ────────
    CLOUDAMQP_URL: str = field(default_factory=lambda: _require("CLOUDAMQP_URL"))
    DASHBOARD_PASSWORD: str = field(default_factory=lambda: _require("DASHBOARD_PASSWORD"))

    # ── Pipeline tuning (optional — safe defaults) ────────────────────────
    NUM_FETCH_WORKERS: int = field(default_factory=lambda: _optional_int("NUM_FETCH_WORKERS", 8))
    NUM_PARSE_WORKERS: int = field(default_factory=lambda: _optional_int("NUM_PARSE_WORKERS", 8))
    NUM_DISCOVERY_WORKERS: int = field(default_factory=lambda: _optional_int("NUM_DISCOVERY_WORKERS", 6))
    MAX_URLS: int = field(default_factory=lambda: _optional_int("MAX_URLS", 500))
    FETCH_DELAY: int = field(default_factory=lambda: _optional_int("FETCH_DELAY", 5))
    FETCH_SLEEP_SEC: int = field(default_factory=lambda: _optional_int("FETCH_SLEEP_SEC", 2))
    DISCOVERY_BACKPRESSURE_THRESHOLD: int = field(default_factory=lambda: _optional_int("DISCOVERY_BACKPRESSURE_THRESHOLD", 50_000))
    CRAWL_TIMEOUT: int = field(default_factory=lambda: _optional_int("CRAWL_TIMEOUT", 8 * 3600))

    # ── SaaS / Production (optional — unlock cloud features when set) ─────
    # Redis: enables Bloom filter URL dedup + shared rate limiting
    REDIS_URL: str = field(default_factory=lambda: _optional("REDIS_URL"))

    # S3: enables cloud raw HTML storage (falls back to local filesystem)
    SARA_S3_BUCKET: str = field(default_factory=lambda: _optional("SARA_S3_BUCKET"))
    SARA_S3_PREFIX: str = field(default_factory=lambda: _optional("SARA_S3_PREFIX", "raw"))
    AWS_DEFAULT_REGION: str = field(default_factory=lambda: _optional("AWS_DEFAULT_REGION", "us-east-1"))

    # API: Bearer token for FastAPI control plane (dev mode if unset)
    SARA_API_KEY: str = field(default_factory=lambda: _optional("SARA_API_KEY"))

    # Observability
    METRICS_PORT: int = field(default_factory=lambda: _optional_int("METRICS_PORT", 8000))
    CORS_ORIGINS: str = field(default_factory=lambda: _optional("CORS_ORIGINS", "*"))

    # Elasticsearch (optional — enables ES upload after parsing)
    ELASTICSEARCH_URL: str = field(default_factory=lambda: _optional("ELASTICSEARCH_URL"))
    ELASTICSEARCH_API_KEY: str = field(default_factory=lambda: _optional("ELASTICSEARCH_API_KEY"))
    ELASTICSEARCH_USER: str = field(default_factory=lambda: _optional("ELASTICSEARCH_USER"))
    ELASTICSEARCH_PASSWORD: str = field(default_factory=lambda: _optional("ELASTICSEARCH_PASSWORD"))

    # Alerting (optional — send failure/success notifications)
    ALERT_EMAIL_TO: str = field(default_factory=lambda: _optional("ALERT_EMAIL_TO"))
    ALERT_EMAIL_FROM: str = field(default_factory=lambda: _optional("ALERT_EMAIL_FROM"))
    ALERT_SMTP_HOST: str = field(default_factory=lambda: _optional("ALERT_SMTP_HOST"))
    ALERT_SMTP_PORT: int = field(default_factory=lambda: _optional_int("ALERT_SMTP_PORT", 587))
    ALERT_SMTP_USER: str = field(default_factory=lambda: _optional("ALERT_SMTP_USER"))
    ALERT_SMTP_PASSWORD: str = field(default_factory=lambda: _optional("ALERT_SMTP_PASSWORD"))
    ALERT_SLACK_WEBHOOK_URL: str = field(default_factory=lambda: _optional("ALERT_SLACK_WEBHOOK_URL"))
    ALERT_NOTIFY_SUCCESS: str = field(default_factory=lambda: _optional("ALERT_NOTIFY_SUCCESS", "false"))

    # ── Properties ────────────────────────────────────────────────────────
    @property
    def redis_enabled(self) -> bool:
        return bool(self.REDIS_URL)

    @property
    def s3_enabled(self) -> bool:
        return bool(self.SARA_S3_BUCKET)

    @property
    def api_auth_enabled(self) -> bool:
        return bool(self.SARA_API_KEY)


# Module-level singleton — imported everywhere
settings = Settings()
