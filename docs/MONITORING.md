# SARA Monitoring Guide

SARA provides multiple layers of observability — structured logs, a live dashboard, Elasticsearch analytics, Kibana visualisations, and Prometheus metrics.

---

## 1. Live Dashboard

The primary monitoring interface is the **Streamlit dashboard** at:

```
https://shanjai.tail1eee4d.ts.net
```

### Dashboard page

Shows all **active crawls** simultaneously (concurrent run support):
- Project, site, schedule ID, current stage
- Per-stage counts: Discovery URLs / Retriever pages / Parser records
- Full history table with filters (project, site, schedule ID)

### System Health page

Real-time health checks for:
- RabbitMQ (connection + queue depths)
- Redis (ping)
- Proxy pool (success rates)
- Elasticsearch (cluster status)
- Storage (disk usage)

---

## 2. Pipeline Logs

All pipeline activity is written to `logs/pipeline.log` as structured JSON with a rotating handler (10 MB × 5 files).

### Log format

Every log line is a JSON object:

```json
{
  "status": "info | success | error",
  "info": "human-readable message",
  "url": "/path/to/file or https://...",
  "crawl": {
    "stage": "discovery | retriever | parser",
    "schedule_id": "20260405",
    "project": "commerce_crawl",
    "site": "myntra_com"
  }
}
```

### Useful log queries

```bash
# All errors for a specific site
grep '"error"' logs/pipeline.log | grep '"site": "myntra_com"'

# All completed runs
grep 'Completed schedule_id' logs/pipeline.log

# Discovery failures (0 URLs found)
grep '"discovery"' logs/pipeline.log | grep '"error"'

# Retriever fetch failures
grep 'Failed to fetch' logs/pipeline.log

# Tail live
tail -f logs/pipeline.log
```

---

## 3. Crawl Status File

`logs/crawl_status.json` tracks progress of all active and recent crawls.

### Structure

```json
{
  "current_runs": {
    "commerce_crawl__myntra_com__20260405": {
      "project": "commerce_crawl",
      "site": "myntra_com",
      "schedule_id": "20260405",
      "stage": "retriever",
      "started_at": "2026-04-05T10:00:00Z",
      "progress": {
        "discovery_urls": 382,
        "retriever_total": 382,
        "retriever_fetched": 150
      }
    }
  },
  "last_runs": [
    {
      "project": "media_crawl",
      "site": "vogue_in",
      "schedule_id": "20260404",
      "status": "completed",
      "started_at": "2026-04-04T02:00:00Z",
      "completed_at": "2026-04-04T03:12:40Z",
      "progress": {
        "discovery_urls": 382,
        "retriever_total": 382,
        "retriever_fetched": 382,
        "parser_pages": 382,
        "parser_records": 382,
        "parser_pages_done": 382
      }
    }
  ]
}
```

```bash
# Pretty-print current status
cat logs/crawl_status.json | python -m json.tool

# Check if any crawl is running
python -c "
import json; d = json.load(open('logs/crawl_status.json'))
print('Active:', list(d.get('current_runs', {}).keys()) or 'None')
"
```

---

## 4. Scheduler Logs

The `sara-scheduler` service logs all scheduled trigger events:

```bash
tail -f ~/SARA/logs/scheduler.log

# Check scheduler service status
sudo systemctl status sara-scheduler

# See upcoming scheduled jobs
python -c "
import json; d = json.load(open('config/schedules.json'))
for project, sites in d.items():
    for site, cfg in sites.items():
        if cfg.get('enabled'):
            print(f'{project}/{site}: {cfg[\"frequency\"]} @ {cfg.get(\"hour\",\"?\")}:{cfg.get(\"minute\",0):02d}')
"
```

---

## 5. Elasticsearch & Kibana

All parsed records are indexed to Elasticsearch progressively during parsing (per-batch upload).

### Kibana access

```
https://shanjai.tail1eee4d.ts.net:8443
```

Login: `elastic` / (your ES password)

### Indices

| Index | Sites |
|-------|-------|
| `sara-commerce-crawl` | Myntra, Flipkart, Ajio, Meesho, Nykaa, etc. |
| `sara-media-crawl` | Vogue, WWD, Drapers, FashionUnited, etc. |

### Key fields

| Field | Type | Description |
|-------|------|-------------|
| `@timestamp` | date | Crawl time (mapped from `crawl_timestamp`) |
| `site_name` | keyword | Filter by site in Kibana |
| `product_name` | text | Product/article title |
| `selling_price` | long | Current price |
| `list_price` | long | MRP / list price |
| `page_url` | keyword | Source URL |

### Kibana queries

```
# All Myntra records from last 7 days
site_name: "myntra_com" AND @timestamp >= now-7d

# Failed price extraction (null selling_price)
site_name: "myntra_com" AND NOT _exists_: selling_price

# Compare sites
site_name: ("myntra_com" OR "ajio_com") AND @timestamp >= now-1d
```

### Check document counts

```bash
python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from core.es_uploader import _get_client
client = _get_client()
for idx in ['sara-commerce-crawl', 'sara-media-crawl']:
    count = client.count(index=idx)['count']
    print(f'{idx}: {count:,} docs')
"
```

---

## 6. Service Health Checks

```bash
# All SARA services at once
for svc in sara-dashboard sara-scheduler elasticsearch kibana rabbitmq-server redis-server; do
    status=$(sudo systemctl is-active $svc)
    echo "$svc: $status"
done

# RabbitMQ queue depths
sudo rabbitmqctl list_queues name messages

# Redis ping
redis-cli ping

# Elasticsearch cluster health
curl -k -u elastic:PASSWORD https://localhost:9200/_cluster/health | python -m json.tool
```

---

## 7. Disk Usage

The pipeline writes HTML files to `scrape_output/retriever_output/` and cache files to `cache/`. Cache files older than 24 hours are auto-deleted.

```bash
# Total output size
du -sh ~/SARA/scrape_output/

# Cache size (auto-cleaned periodically)
du -sh ~/SARA/cache/

# Manual cache cleanup (delete all files older than 1 day)
find ~/SARA/cache -name "*.html" -mtime +1 -delete

# Parser output CSVs
ls -lh ~/SARA/scrape_output/parser_output/**/**/*.csv 2>/dev/null
```

---

## 8. Prometheus Metrics

SARA exposes Prometheus metrics on port 8000 (configurable via `METRICS_PORT`):

```bash
# Check metrics endpoint
curl http://localhost:8000/metrics

# Key metrics
sara_urls_discovered_total    # URLs found by discovery (labels: project, site)
sara_pages_fetched_total      # Pages fetched by retriever
sara_records_parsed_total     # Records extracted by parser
sara_fetch_errors_total       # HTTP fetch failures
sara_parse_errors_total       # Parsing failures
sara_fetch_duration_seconds   # Histogram of fetch latency
```

---

## 9. Alerts to Set Up

| Alert | Condition | Action |
|-------|-----------|--------|
| Crawl failed | `status: "failed"` in last_runs | Check pipeline.log for the failing stage |
| 0 URLs discovered | `discovery_urls: 0` in completed run | Site may be blocking — check discovery YAML and try proxy |
| Low fetch rate | `retriever_fetched / retriever_total < 0.5` | HTTP errors — check extended_header or proxy config |
| Elasticsearch down | `sara-es` tunnel unreachable | `sudo systemctl restart elasticsearch` |
| Scheduler not running | `sara-scheduler` inactive | `sudo systemctl restart sara-scheduler` |
| Disk > 80% | `df -h` shows > 80% | Run cache cleanup + archive old scrape_output |

---

## 10. Quick Diagnostic Checklist

When a crawl fails, check in order:

```bash
# 1. What stage failed?
cat logs/crawl_status.json | python -m json.tool | grep -A5 '"status": "failed"'

# 2. What was the error?
grep '"error"' logs/pipeline.log | tail -20

# 3. Is RabbitMQ healthy?
sudo systemctl status rabbitmq-server
sudo rabbitmqctl list_queues

# 4. Is the site's discovery YAML correct?
cat url_discovery/<project>/<site>_<project>.yml

# 5. Is the parser YAML missing a field?
cat url_data_parser/<project>/<site>_<project>.yml

# 6. Did ES upload succeed?
grep 'ES upload' logs/pipeline.log | tail -5
```
