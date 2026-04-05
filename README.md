# SARA — Scalable Automated Retrieval Architecture

SARA is a production-grade web data pipeline for fashion e-commerce and media intelligence. It discovers URLs, fetches pages, parses structured records, and indexes them into Elasticsearch — with a full Streamlit dashboard, per-site scheduling, and public HTTPS access via Tailscale Funnel.

---

## Live URLs

| Service | URL |
|---------|-----|
| SARA Dashboard | `https://shanjai.tail1eee4d.ts.net` |
| Kibana (Data Explorer) | `https://shanjai.tail1eee4d.ts.net:8443` |
| Elasticsearch | `https://shanjai.tail1eee4d.ts.net:10000` |

---

## Architecture Overview

```
  ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
  │  Discovery  │────▶│  RabbitMQ    │────▶│  Retriever  │
  │  (per site) │     │  URL Queue   │     │  (parallel) │
  └─────────────┘     └──────────────┘     └──────┬──────┘
                                                   │ HTML files
                                            ┌──────▼──────┐
                                            │   Parser    │
                                            │  (threaded) │
                                            └──────┬──────┘
                                                   │ CSV + progressive ES upload
                                     ┌─────────────▼──────────────┐
                                     │     Elasticsearch          │
                                     │  sara-commerce-crawl       │
                                     │  sara-media-crawl          │
                                     └────────────────────────────┘
```

**Pipeline stages run concurrently**: discovery pushes URLs to RabbitMQ while retriever starts consuming — no waiting for discovery to finish.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Pipeline orchestration | Python subprocesses (concurrent Popen) |
| URL queue | RabbitMQ (pika) |
| HTTP fetching | requests + per-thread Session pool |
| Rate limiting | `core/rate_limiter.py` — per-domain token bucket |
| Data storage | Local filesystem (CSV + HTML) |
| Search/analytics | Elasticsearch 8.x + Kibana |
| Dashboard | Streamlit |
| Scheduling | APScheduler (per-site frequency via dashboard) |
| Public access | Tailscale Funnel (permanent HTTPS URLs) |
| Cache | Redis (rate limiter state) |
| Async workers | `services/retriever/worker.py`, `services/discovery/worker.py` (built, additive) |
| API | FastAPI (`services/api/main.py`, port 8080) |
| Observability | Prometheus metrics + structured JSON logging |

---

## Directory Layout

```
SARA/
├── crawl_runner.py              # Pipeline orchestrator (discovery → retriever → parser)
├── creation_script.py           # Scaffolds new project/site configs
├── delete_files_automated.py    # Removes project/site configs
├── proxy_config.py              # Proxy list loader (WEBSHARE_PROXY_JSON)
├── setup_server.sh              # One-shot server setup (systemd services, tunnels, cron)
├── show_urls.sh                 # Print current tunnel URLs
│
├── config/
│   ├── settings.py              # Centralised settings (env vars → dataclass)
│   └── schedules.json           # Per-site crawl schedules (managed via dashboard)
│
├── core/                        # Shared infrastructure modules
│   ├── broker.py                # RabbitMQ abstraction (sync + async, DLX topology)
│   ├── dedup.py                 # Redis Bloom Filter + FileBloomFilter fallback
│   ├── rate_limiter.py          # Per-domain rate limiting (sync + async)
│   ├── proxy_manager.py         # Smart proxy rotation with health tracking
│   ├── metrics.py               # Prometheus instrumentation
│   ├── storage.py               # LocalStorage / S3Storage abstraction
│   ├── change_detection.py      # Content-hash change detection
│   └── es_uploader.py           # Elasticsearch bulk uploader
│
├── sdf_module/                  # Core pipeline drivers
│   ├── files_import.py          # Central imports and shared constants
│   ├── sdf_fetch.py             # HTTP fetching, retries, logging, RabbitMQ helpers
│   ├── url_discovery.py         # Discovery stage driver
│   ├── url_retriever.py         # Retriever stage driver (rate-limited, deduped)
│   ├── url_parser.py            # Parser stage driver (streaming CSV + progressive ES)
│   └── crawl_status.py          # Concurrent crawl progress tracking
│
├── services/                    # Async worker services (additive, not replacing sync)
│   ├── discovery/worker.py      # Async discovery worker (aiohttp + RabbitMQ)
│   ├── retriever/worker.py      # Async retriever worker (semaphore-bounded)
│   ├── scheduler/worker.py      # APScheduler — reads schedules.json, triggers crawls
│   └── api/                     # FastAPI control plane (port 8080)
│       ├── main.py              # App entrypoint, auth, CORS, lifespan hooks
│       ├── routers/crawls.py    # Crawl trigger, status, DLQ endpoints
│       ├── routers/sites.py     # Site CRUD endpoints
│       └── schemas.py           # Pydantic v2 request/response models
│
├── dashboard/
│   └── streamlit_app.py         # Full Streamlit dashboard (all pages)
│
├── url_discovery/               # Per-site discovery logic
│   └── <project>/
│       ├── <site>_<project>.py  # Discovery methods (pagination, product URLs)
│       └── <site>_<project>.yml # Depth config + seed URLs
│
├── url_data_parser/             # Per-site parser logic
│   ├── commerce_crawl/
│   │   └── <site>_commerce_crawl.{py,yml}
│   └── media_crawl/
│       └── <site>_media_crawl.{py,yml}
│
├── scrape_output/
│   ├── discovery_output/        # Discovery TXT files
│   ├── retriever_output/        # Fetched HTML + metadata queue files
│   └── parser_output/           # Extracted CSV files
│
├── logs/
│   ├── pipeline.log             # Rotating structured JSON log (10MB × 5)
│   ├── crawl_status.json        # Live crawl progress (concurrent runs supported)
│   └── scheduler.log            # Scheduler service log
│
└── infra/
    ├── docker-compose.yml       # Full stack: RabbitMQ, Redis, Prometheus, Grafana, API, Dashboard
    ├── prometheus.yml           # Scrape configs
    ├── Dockerfile.api           # FastAPI container
    ├── Dockerfile.dashboard     # Streamlit container
    └── Dockerfile.worker        # Generic worker container
```

---

## Quick Start

### Run a crawl manually

```bash
source venv/bin/activate
python crawl_runner.py <project> <site> <schedule_id>

# Examples:
python crawl_runner.py commerce_crawl myntra_com 20260405
python crawl_runner.py media_crawl vogue_in 20260405
```

### Run individual stages

```bash
python -m sdf_module.url_discovery commerce_crawl myntra_com 20260405
python -m sdf_module.url_retriever commerce_crawl myntra_com 20260405
python -m sdf_module.url_parser    commerce_crawl myntra_com 20260405
```

---

## Environment Variables (`.env`)

### Required

| Variable | Description |
|----------|-------------|
| `CLOUDAMQP_URL` | RabbitMQ connection URL (e.g. `amqp://guest:guest@localhost:5672/`) |
| `DASHBOARD_PASSWORD` | Password to access the Streamlit dashboard |
| `WEBSHARE_PROXY_JSON` | JSON array of proxy tuples (`[]` if not using proxies) |

### Optional — pipeline tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `NUM_FETCH_WORKERS` | 4 | Parallel threads for URL retrieval |
| `NUM_PARSE_WORKERS` | 4 | Parallel threads for HTML parsing |
| `MAX_URLS` | 500 | Max URLs pulled from queue per run |
| `FETCH_DELAY` | 5 | Seconds between discovery calls |
| `FETCH_SLEEP_SEC` | 2 | Fallback sleep between retriever fetches |

### Optional — SaaS / production

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Redis URL — enables shared rate limiting |
| `ELASTICSEARCH_URL` | ES URL — enables auto-upload after parsing |
| `ELASTICSEARCH_USER` | ES username |
| `ELASTICSEARCH_PASSWORD` | ES password |
| `ELASTICSEARCH_API_KEY` | ES API key (alternative to user/pass) |
| `SARA_S3_BUCKET` | S3 bucket — enables cloud HTML storage |
| `SARA_API_KEY` | Bearer token for FastAPI control plane |
| `METRICS_PORT` | Prometheus metrics server port (default: 8000) |
| `CORS_ORIGINS` | Comma-separated allowed origins for API CORS |

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| Dashboard | Live crawl progress (concurrent runs), history table with filters |
| Run Crawl | Manually trigger a crawl for any project/site |
| Create Project | Scaffold new project + site config files |
| Delete Project | Remove project/site config files |
| Manage Data | Browse and download parser output CSV files |
| Projects and Sites | List all configured sites |
| **Schedules** | Set per-site crawl frequency (hourly/daily/weekly/custom) via UI |
| Analytics | Plotly charts — throughput, funnel, site comparison |
| DLQ Inspector | Peek/requeue/purge dead-letter queue messages |
| System Health | RabbitMQ, Redis, proxy pool, storage health checks |
| API Access | Live API ping, endpoint reference, code examples |

---

## Services (systemd)

All services auto-start on reboot:

| Service | Description | Port |
|---------|-------------|------|
| `sara-dashboard` | Streamlit dashboard | 8501 |
| `sara-scheduler` | APScheduler crawl trigger | — |
| `elasticsearch` | Elasticsearch | 9200 |
| `kibana` | Kibana | 5601 |
| `rabbitmq-server` | RabbitMQ | 5672 |
| `redis-server` | Redis | 6379 |
| `cf-sara-dashboard` | Cloudflare quick tunnel for dashboard | — |
| `cf-sara-kibana` | Cloudflare quick tunnel for Kibana | — |
| `cf-sara-es` | Cloudflare quick tunnel for ES | — |

```bash
# Check status of all SARA services
sudo systemctl status sara-dashboard sara-scheduler elasticsearch kibana

# View scheduler logs
tail -f ~/SARA/logs/scheduler.log

# View pipeline logs
tail -f ~/SARA/logs/pipeline.log
```

---

## Elasticsearch Indices

| Index | Contents |
|-------|----------|
| `sara-commerce-crawl` | All commerce sites (Myntra, Flipkart, Ajio, etc.) |
| `sara-media-crawl` | All media sites (Vogue, WWD, Drapers, etc.) |

Each document has:
- All parsed fields from the site YAML config
- `site_name` — keyword field for filtering by site in Kibana
- `@timestamp` — mapped from `crawl_timestamp` for Kibana time-based views

### Backfill existing CSVs to ES

```bash
python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from pathlib import Path
from core.es_uploader import upload_all_existing
print(f'Uploaded: {upload_all_existing(Path(\".\"))} docs')
"
```

---

## Scheduling

Per-site crawl schedules are managed via the dashboard **Schedules** page. Schedules are stored in `config/schedules.json`. The `sara-scheduler` service picks up changes within 5 minutes.

Supported frequencies:
- `disabled` — no automatic crawling
- `hourly` — every hour at configured minute
- `daily` — every day at configured hour:minute (IST)
- `weekly` — every week on configured day + hour:minute
- `custom` — full cron expression (e.g. `0 2 * * 1-5`)

---

## Adding a New Site

### 1. Scaffold

```bash
python creation_script.py <project_name> <site_name>
```

Creates boilerplate `.py` and `.yml` for discovery and parser.

### 2. Implement discovery

Edit `url_discovery/<project>/<site>_<project>.py`:
- Add seed URLs to YAML `depth0.seed_url`
- Implement depth methods (e.g. `get_pagination_url`, `get_product_url`)

### 3. Implement parser

Edit `url_data_parser/<project>/<site>_<project>.py`:
- Implement `get_<field>` methods for each field in the YAML
- Always guard XPath results: `elems[0].text if elems else None`

### 4. Run and validate

```bash
python crawl_runner.py <project> <site> <schedule_id>
```

Check output:
- `logs/pipeline.log` — structured JSON logs
- `scrape_output/parser_output/` — CSV files
- Kibana → Discover → filter `site_name: <site>` — ES records

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Concurrent discovery + retrieval | Retriever starts consuming as soon as discovery pushes first URLs — no waiting for full discovery |
| Per-domain rate limiting | `core/rate_limiter.py` enforces domain-specific delays to avoid blocks |
| Progressive ES upload | Records indexed to ES per-batch during parsing, not all at end |
| In-memory URL dedup | Duplicate URLs within a crawl run are skipped before fetching |
| RabbitMQ queue deleted after consuming | Prevents stale queue accumulation across runs |
| Pre-flight health check | RabbitMQ connectivity verified before pipeline starts |
| Cache auto-cleanup | HTML cache files older than 24h are deleted to prevent disk fill |
| Concurrent crawl status | `crawl_status.json` tracks multiple simultaneous crawls independently |
| Two ES indices only | `sara-commerce-crawl` and `sara-media-crawl` with `site_name` field for filtering |

---

## Monitoring

```bash
# Live pipeline log
tail -f logs/pipeline.log

# Current crawl status
cat logs/crawl_status.json | python -m json.tool

# Check all service health
sudo systemctl status sara-dashboard sara-scheduler elasticsearch kibana rabbitmq-server redis-server

# Tunnel URLs
bash show_urls.sh
```

See `docs/MONITORING.md` for detailed monitoring guide.
