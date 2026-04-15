# SARA — Scalable Automated Retrieval Architecture

SARA is a production-grade web data pipeline for fashion e-commerce and media intelligence. It discovers URLs, fetches pages, parses structured records, and indexes them into Elasticsearch — with a Streamlit dashboard, per-site scheduling, distributed worker pool, and crawl failure alerting.

---

## Architecture Overview

```
  ┌──────────────┐     job JSON     ┌──────────────────────┐
  │  Scheduler   │ ──────────────▶  │  sara-crawl-jobs     │  RabbitMQ
  │ (APScheduler)│                  │  (priority queue)    │
  └──────────────┘                  └──────────┬───────────┘
                                               │ pull (auto_ack)
                         ┌─────────────────────┼─────────────────────┐
                         ▼                     ▼                     ▼
                   sara-worker@1        sara-worker@2    …    sara-worker@5
                         │
                         ▼  crawl_runner.py
          ┌──────────────────────────────────────┐
          │         3-stage pipeline              │
          │                                      │
          │  ┌──────────┐    URL queue    ┌─────────────┐
          │  │Discovery │ ─────────────▶  │  Retriever  │
          │  │(per site)│   (RabbitMQ)    │  (parallel) │
          │  └──────────┘                └──────┬──────┘
          │                                     │  HTML files
          │                              ┌──────▼──────┐
          │                              │   Parser    │
          │                              │  (threaded) │
          │                              └──────┬──────┘
          │                                     │  CSV → ES
          └──────────────────────────────────────┘
                                               │
                               ┌───────────────▼───────────────┐
                               │         Elasticsearch          │
                               │   sara-commerce-crawl          │
                               │   sara-media-crawl             │
                               └───────────────────────────────┘
```

**How it works:**
- Scheduler dispatches job JSON to a RabbitMQ priority queue at scheduled times
- 5 worker processes poll the queue — each runs one full crawl at a time
- Inside each crawl: discovery and retriever run concurrently; parser runs after both finish
- On failure/success: alerts sent via email and/or Slack

---

## Sites

### Media Crawl (11 sites)

| Site | Pagination | Proxy |
|------|-----------|-------|
| `apparel_resources_com` | WordPress `/page/N/` | — |
| `drapers_com` | `?page=N` | webshare_proxy |
| `fashion_united_global_com` | `?page=N` | — |
| `fashion_united_in` | `?page=N` | — |
| `vogue_in` | `?page=N` | webshare_proxy |
| `wwd_com` | WordPress `/page/N/` | webshare_proxy |
| `fibre_2_fashion_com` | `/N/` path suffix | — |
| `just_style_com` | WordPress `/page/N/` | webshare_proxy |
| `the_fashion_law_com` | WordPress `/page/N/` | — |
| `the_industry_fashion_com` | WordPress `/page/N/` | — |
| `business_of_fashion` | `?page=N` | webshare_proxy |

### Commerce Crawl (11 sites)

| Site | Product URL pattern | Proxy |
|------|-------------------|-------|
| `ajio_com` | `/p/` | webshare_proxy |
| `amazon_in` | `/dp/` | webshare_proxy |
| `flipkart_com` | `/p/`, `/product/` | — |
| `myntra_com` | ends with `/buy` | webshare_proxy |
| `meesho_com` | `/p/`, `/product/` | webshare_proxy |
| `limeroad_com` | `/p/`, `/story/`, `/product/` | — |
| `max_com` | `/p/`, `/product/` | — |
| `nykaa_fashion_com` | `/p/`, `/product/` | webshare_proxy |
| `shoppersstop_com` | `/p/`, `/p-`, `/product/` | — |
| `styleunion_com` | Shopify card ID | — |
| `tata_cliq_com` | `/p/`, `/p-`, `/product/` | — |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Pipeline orchestration | Python subprocesses (concurrent Popen) |
| Job distribution | RabbitMQ `sara-crawl-jobs` priority queue |
| Worker pool | 5 × `services/worker/main.py` (systemd template) |
| URL queue | RabbitMQ per-site queue (auto-deleted after drain) |
| HTTP fetching | `requests` + per-thread Session pool |
| Rate limiting | `core/rate_limiter.py` — per-domain token bucket |
| Deduplication | Redis `SyncBloomFilter` / `FileBloomFilter` fallback |
| Data storage | Local filesystem (CSV + HTML) |
| Search/analytics | Elasticsearch 8.x + Kibana |
| Dashboard | Streamlit |
| Scheduling | APScheduler (per-site frequency via dashboard) |
| Alerting | Email (SMTP) + Slack webhook on crawl failure |
| Proxy | Webshare rotating proxy pool |
| Public access | Cloudflare quick tunnels |
| API | FastAPI (`services/api/main.py`, port 8080) |
| Observability | Prometheus metrics + structured JSON logging |

---

## Directory Layout

```
SARA/
├── crawl_runner.py              # Pipeline orchestrator (discovery → retriever → parser)
├── creation_script.py           # Scaffolds new project/site config files
├── proxy_config.py              # Proxy list loader (WEBSHARE_PROXY_JSON)
├── setup_server.sh              # One-shot server setup (all systemd services)
├── show_urls.sh                 # Print current Cloudflare tunnel URLs
│
├── config/
│   ├── settings.py              # Centralised env → dataclass settings
│   └── schedules.json           # Per-site crawl schedules (managed via dashboard)
│
├── core/                        # Shared infrastructure
│   ├── alerting.py              # Email + Slack failure/success alerts
│   ├── broker.py                # RabbitMQ abstraction
│   ├── dedup.py                 # SyncBloomFilter (Redis) + FileBloomFilter fallback
│   ├── discovery_helpers.py     # Pagination helpers (wordpress_pages, querystring_pages…)
│   ├── rate_limiter.py          # Per-domain rate limiting (sync + async)
│   ├── proxy_manager.py         # Smart proxy rotation with health tracking
│   ├── metrics.py               # Prometheus instrumentation
│   ├── storage.py               # LocalStorage / S3Storage abstraction
│   ├── change_detection.py      # Content-hash change detection
│   └── es_uploader.py           # Elasticsearch bulk uploader
│
├── sdf_module/                  # Core pipeline drivers
│   ├── files_import.py          # Central imports and shared constants
│   ├── sdf_fetch.py             # HTTP fetching, retries, proxy, caching
│   ├── url_discovery.py         # Discovery stage (rate-limited, batched RabbitMQ publish)
│   ├── url_retriever.py         # Retriever stage (queue drain, cross-run dedup)
│   ├── url_parser.py            # Parser stage (one-page-per-task, deferred ES upload)
│   └── crawl_status.py          # Thread + file-locked crawl progress tracking
│
├── services/
│   ├── scheduler/worker.py      # Dispatcher — publishes job JSON to sara-crawl-jobs
│   ├── worker/main.py           # Crawl worker — polls queue, runs crawl_runner.py
│   └── api/                     # FastAPI control plane (port 8080)
│
├── tools/                       # Developer testing tools
│   ├── test_discovery.py        # Run discovery for a site without RabbitMQ
│   ├── test_xpath.py            # Test XPath expressions against a live URL
│   └── validate_site.py         # Validate all 22 sites import and are wired correctly
│
├── dashboard/
│   └── streamlit_app.py         # Full Streamlit dashboard
│
├── url_discovery/               # Per-site discovery logic
│   └── <project>/
│       ├── <site>_<project>.py  # Pagination + URL filter methods
│       └── <site>_<project>.yml # Seed URLs + depth config + request_params
│
├── url_data_parser/             # Per-site parser logic
│   ├── commerce_crawl/
│   │   └── <site>_commerce_crawl.{py,yml}
│   └── media_crawl/
│       └── <site>_media_crawl.{py,yml}
│
├── scrape_output/
│   ├── discovery_output/        # Discovery URL text files
│   ├── retriever_output/        # Fetched HTML + metadata queue files
│   └── parser_output/           # Extracted CSV files
│
└── logs/
    ├── pipeline.log             # Rotating structured log (10MB × 5 files)
    ├── crawl_status.json        # Live crawl progress (concurrent runs)
    ├── scheduler.log            # Scheduler service log
    ├── worker-1.log             # Per-worker logs
    ├── worker-2.log
    └── …
```

---

## Quick Start

### Run a full crawl (full pipeline)

```bash
source venv/bin/activate
python crawl_runner.py <project> <site> <schedule_id>

# Examples
python crawl_runner.py media_crawl fashion_united_global_com test001
python crawl_runner.py commerce_crawl flipkart_com test001
```

### Run individual stages (debugging)

```bash
# 1. Discovery — finds URLs and pushes to RabbitMQ
python -m sdf_module.url_discovery media_crawl fashion_united_global_com test001

# 2. Retriever — fetches HTML for each discovered URL
python -m sdf_module.url_retriever media_crawl fashion_united_global_com test001

# 3. Parser — extracts fields, writes CSV, uploads to ES
python -m sdf_module.url_parser media_crawl fashion_united_global_com test001
```

### Test without running a real crawl

```bash
# Check what URLs a site discovers (no RabbitMQ, no side effects)
python -m tools.test_discovery media_crawl apparel_resources_com --depth 1 --limit 5
python -m tools.test_discovery commerce_crawl ajio_com --depth 1 --limit 5

# Test XPath expressions against a live URL
python -m tools.test_xpath "https://fashionunited.com/news/fashion/some-article" \
    "//meta[@property='og:title']/@content" "//article//p//text()"

# Validate all 22 sites are correctly wired (imports, YAML, methods)
python -m tools.validate_site --all
```

**Best sites to start testing** (SSR, open access, no paywall):
- `media_crawl fashion_united_global_com`
- `media_crawl apparel_resources_com`
- `commerce_crawl flipkart_com`
- `commerce_crawl styleunion_com`

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `CLOUDAMQP_URL` | RabbitMQ connection URL (e.g. `amqp://guest:guest@localhost:5672/`) |
| `DASHBOARD_PASSWORD` | Password to access the Streamlit dashboard |
| `WEBSHARE_PROXY_JSON` | JSON array of proxy tuples — set to `[]` if not using proxies |

### Elasticsearch

| Variable | Description |
|----------|-------------|
| `ELASTICSEARCH_URL` | ES URL (e.g. `https://localhost:9200`) |
| `ELASTICSEARCH_USER` | ES username (default: `elastic`) |
| `ELASTICSEARCH_PASSWORD` | ES password |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | — | Redis URL — enables cross-run Bloom filter deduplication. Falls back to file-based dedup if unset |

### Alerting — Email (all optional)

| Variable | Description |
|----------|-------------|
| `ALERT_EMAIL_TO` | Recipient address(es) for crawl failure alerts (comma-separated) |
| `ALERT_EMAIL_FROM` | Sender address shown in From header |
| `ALERT_SMTP_HOST` | SMTP server (e.g. `smtp.gmail.com`) |
| `ALERT_SMTP_PORT` | SMTP port (default: `587`) |
| `ALERT_SMTP_USER` | SMTP username |
| `ALERT_SMTP_PASSWORD` | SMTP password (use Gmail App Password if 2FA enabled) |

### Alerting — Slack (optional)

| Variable | Description |
|----------|-------------|
| `ALERT_SLACK_WEBHOOK_URL` | Incoming webhook URL from your Slack app |
| `ALERT_NOTIFY_SUCCESS` | Set to `true` to also alert on success (default: `false`) |

### Pipeline Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `NUM_FETCH_WORKERS` | 4 | Parallel threads for URL retrieval |
| `NUM_PARSE_WORKERS` | 4 | Parallel threads for HTML parsing |
| `MAX_URLS` | 500 | Max URLs pulled from queue per run |
| `FETCH_DELAY` | 5 | Seconds between discovery depth calls |
| `FETCH_SLEEP_SEC` | 2 | Fallback sleep between retriever fetches |

---

## Services (systemd)

All services auto-start on reboot. Managed by `setup_server.sh`.

| Service | Description | Port |
|---------|-------------|------|
| `sara-dashboard` | Streamlit dashboard | 8501 |
| `sara-scheduler` | APScheduler — dispatches jobs to queue | — |
| `sara-worker@1` … `sara-worker@5` | Crawl workers — poll queue, run crawls | — |
| `elasticsearch` | Elasticsearch | 9200 |
| `kibana` | Kibana | 5601 |
| `rabbitmq-server` | RabbitMQ | 5672 |
| `redis-server` | Redis | 6379 |
| `cf-sara-dashboard` | Cloudflare tunnel → dashboard | — |
| `cf-sara-kibana` | Cloudflare tunnel → Kibana | — |
| `cf-sara-es` | Cloudflare tunnel → ES | — |

```bash
# Check all SARA services
sudo systemctl status sara-dashboard sara-scheduler 'sara-worker@*'

# Start/stop individual worker
sudo systemctl start sara-worker@3
sudo systemctl stop sara-worker@3

# View worker logs
tail -f ~/SARA/logs/worker-1.log
tail -f ~/SARA/logs/worker-2.log

# View pipeline log
tail -f ~/SARA/logs/pipeline.log

# View scheduler log
tail -f ~/SARA/logs/scheduler.log
```

---

## Scheduling

Per-site crawl schedules are managed via the dashboard **Schedules** page. Stored in `config/schedules.json`. The `sara-scheduler` dispatcher reads this file and publishes job JSON to `sara-crawl-jobs` RabbitMQ queue at the scheduled time. Workers pick up and run the jobs.

Supported frequencies:
- `disabled` — no automatic crawling
- `hourly` — every hour at configured minute
- `daily` — every day at configured hour:minute (IST)
- `weekly` — every week on configured day + hour:minute
- `custom` — full cron expression (e.g. `0 2 * * 1-5`)

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| Dashboard | Live crawl progress, history table with filters |
| Run Crawl | Manually trigger a crawl for any project/site |
| Create Project | Scaffold new project + site config files |
| Delete Project | Remove project/site config files |
| Manage Data | Browse and download parser output CSV files |
| Projects and Sites | List all 22 configured sites |
| Schedules | Set per-site crawl frequency via UI |
| Analytics | Plotly charts — throughput, funnel, site comparison |
| DLQ Inspector | Peek/requeue/purge dead-letter queue messages |
| System Health | RabbitMQ, Redis, proxy pool, storage health checks |
| API Access | Live API ping, endpoint reference, code examples |

---

## Elasticsearch Indices

| Index | Contents |
|-------|----------|
| `sara-commerce-crawl` | All commerce sites (Myntra, Flipkart, Ajio, etc.) |
| `sara-media-crawl` | All media sites (Vogue, WWD, Drapers, etc.) |

Each document includes all parsed fields from the site YAML config plus `site_name` (for Kibana filtering) and `@timestamp` (from `crawl_timestamp`).

### Backfill existing CSVs to ES

```bash
cd ~/SARA && source venv/bin/activate
python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from pathlib import Path
from core.es_uploader import upload_all_existing
print(f'Backfilled: {upload_all_existing(Path(\".\"))} docs')
"
```

---

## Adding a New Site

### 1. Scaffold boilerplate

```bash
python creation_script.py <project_name> <site_name>
# e.g. python creation_script.py media_crawl mynewsite_com
```

Creates `.py` and `.yml` for both discovery and parser.

### 2. Implement discovery (`url_discovery/<project>/<site>_<project>.py`)

```python
from sdf_module.url_discovery import *
from core.discovery_helpers import wordpress_pages, querystring_pages

class MynewsiteComMediaCrawl():

    def get_pagination_url(self, keyurl, depth, current_depth_level):
        # WordPress sites:
        return wordpress_pages(keyurl, count=15)
        # Querystring sites:
        # return querystring_pages(keyurl, count=15)

    def get_product_url(self, url, depth, current_depth_level):
        product_url = []
        dom = sdfFetch.get_page_content_hash(url)
        if dom.get("status_code") != 200:
            return product_url
        parsed_tree = html.fromstring(dom.get("page_doc", ""))
        for link in parsed_tree.xpath("//a[@href]/@href"):
            full = urljoin(url, link)
            if "mynewsite.com" not in urlparse(full).netloc:
                continue
            if "/article/" not in full:
                continue
            product_url.append(full)
        return product_url  # no [:N] cap
```

Set seed URLs and optionally `request_params` in the YAML:
```yaml
depth0:
  seed_url: ["https://mynewsite.com/news/"]
  method_name: get_pagination_url
depth1:
  method_name: get_product_url
request_params:
  timeout: 30
  max_retries: 3
  # proxy: webshare_proxy   # uncomment if site blocks scrapers
```

### 3. Implement parser (`url_data_parser/<project>/<site>_<project>.py`)

```python
from sdf_module.url_parser import *

class MynewsiteComMediaCrawl():
    @staticmethod
    def get_crawl_timestamp(page_doc, inhash):
        return datetime.now().strftime("%b %d, %Y @ %H:%M:%S.%f")[:-3]

    @staticmethod
    def get_uniq_id(page_doc, inhash):
        return sdfFetch.encode(str(inhash))

    @staticmethod
    def get_page_url(page_doc, inhash):
        return str(inhash)

    @staticmethod
    def get_article_title(page_doc, inhash):
        elems = page_doc.xpath("//meta[@property='og:title']/@content | //h1/text()")
        return elems[0].strip() if elems else ""
```

### 4. Validate and test

```bash
# Check site is wired correctly
python -m tools.validate_site --all

# Test discovery without RabbitMQ
python -m tools.test_discovery media_crawl mynewsite_com --depth 1 --limit 5

# Test XPath on a real article
python -m tools.test_xpath "https://mynewsite.com/article/test" "//h1/text()"

# Run full pipeline
python crawl_runner.py media_crawl mynewsite_com test001
```

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Scheduler dispatches, workers execute | Scheduler only publishes job JSON; 5 independent workers consume — horizontal scale without code changes |
| `auto_ack` + reconnect-per-job | Crawls take 8h — manual ACK requires keeping connection alive which kills RabbitMQ heartbeats. Scheduler re-dispatches if a worker crashes |
| SIGTERM propagation in workers | `systemctl stop sara-worker@N` terminates the child `crawl_runner.py` process cleanly instead of orphaning it |
| Concurrent discovery + retrieval | Retriever starts consuming as soon as discovery pushes first URLs — no waiting for full discovery |
| Per-domain rate limiting | `core/rate_limiter.py` enforces domain-specific delays per discovery and retriever thread |
| One-page-per-task in parser | Peak RAM = `NUM_PARSE_WORKERS × 1 lxml tree` regardless of total page count |
| Deferred ES upload | Single `upload_csv()` call after ThreadPoolExecutor exits — no lock contention during parsing |
| Cross-run Bloom filter dedup | Redis `SyncBloomFilter` persisted per site prevents re-fetching URLs already seen in previous runs |
| RabbitMQ batch publish (100/batch) | Avoids 5000 individual RPC round-trips during discovery |
| RabbitMQ queue deleted after drain | Prevents stale accumulation across runs |
| No `[:N]` cap on discovered URLs | Discovery returns all URLs found per page — previously capped at 10, silently dropping most products |
| Pre-flight health check | RabbitMQ connectivity verified before pipeline starts |
| File + thread locking on crawl_status | `crawl_status.json` uses both `threading.Lock` and `fcntl.flock` for safe concurrent writes from multiple workers |

---

## Monitoring

```bash
# Live pipeline log
tail -f logs/pipeline.log

# Current crawl status (all running crawls)
cat logs/crawl_status.json | python -m json.tool

# All worker statuses
sudo systemctl status 'sara-worker@*'

# Check all service health
sudo systemctl status sara-dashboard sara-scheduler elasticsearch kibana rabbitmq-server redis-server

# Tunnel URLs (Cloudflare)
bash show_urls.sh
```

See `docs/MONITORING.md` for the detailed monitoring guide.
