# SARA Server Setup Guide

Complete step-by-step guide to deploy SARA on a fresh Ubuntu server. Follow this whenever migrating to a new machine.

---

## Prerequisites

- Ubuntu 22.04 or 24.04 (server or desktop)
- Minimum 4 GB RAM, 50 GB disk
- Internet access
- A GitHub account with access to the SARA repo

---

## Step 1: Update System

```bash
sudo apt update && sudo apt upgrade -y
```

---

## Step 2: Install System Dependencies

```bash
sudo apt install -y \
    python3 python3-pip python3-venv \
    git curl wget \
    rabbitmq-server \
    redis-server
```

---

## Step 3: Install Elasticsearch + Kibana

```bash
# Add Elastic APT repo
curl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | \
    sudo gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] \
    https://artifacts.elastic.co/packages/8.x/apt stable main" | \
    sudo tee /etc/apt/sources.list.d/elastic-8.x.list

sudo apt update
sudo apt install -y elasticsearch kibana
```

**Save the elastic superuser password** printed during install. If you miss it:
```bash
sudo /usr/share/elasticsearch/bin/elasticsearch-reset-password -u elastic
```

Enable and start:
```bash
sudo systemctl enable elasticsearch kibana
sudo systemctl start elasticsearch kibana
```

Verify Elasticsearch is running:
```bash
curl -k -u elastic:YOUR_PASSWORD https://localhost:9200
```

Configure Kibana to accept external connections:
```bash
sudo nano /etc/kibana/kibana.yml
# Set: server.host: "0.0.0.0"
sudo systemctl restart kibana
```

---

## Step 4: Install Cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
    -o cloudflared.deb
sudo dpkg -i cloudflared.deb
rm cloudflared.deb
```

---

## Step 5: Clone SARA

```bash
cd ~
git clone https://github.com/shanjai1511/SARA.git
cd SARA
```

---

## Step 6: Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install "elasticsearch>=8.0.0,<9.0.0"   # pin to ES 8.x client
```

---

## Step 7: Create `.env` File

```bash
cp ~/SARA/.env.example ~/SARA/.env
nano ~/SARA/.env
```

Fill in all values:

```env
# ── RabbitMQ ──────────────────────────────────────────────────────────────────
CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/

# ── Elasticsearch ─────────────────────────────────────────────────────────────
ELASTICSEARCH_URL=https://localhost:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=your_elastic_password_here

# ── Redis (enables cross-run Bloom filter deduplication) ──────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Proxy credentials ─────────────────────────────────────────────────────────
# JSON array of [host, port, username, password] — set [] if no proxies
WEBSHARE_PROXY_JSON=[]

# ── Dashboard ─────────────────────────────────────────────────────────────────
DASHBOARD_PASSWORD=your_secure_password_here

# ── Alerting — Email (all optional) ──────────────────────────────────────────
ALERT_EMAIL_TO=you@example.com
ALERT_EMAIL_FROM=sara-alerts@yourdomain.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=your-gmail@gmail.com
ALERT_SMTP_PASSWORD=your-gmail-app-password
# ALERT_NOTIFY_SUCCESS=true   # uncomment to also alert on success

# ── Alerting — Slack (optional) ───────────────────────────────────────────────
# ALERT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ

# ── Pipeline tuning ───────────────────────────────────────────────────────────
NUM_FETCH_WORKERS=4
NUM_PARSE_WORKERS=4
MAX_URLS=500
FETCH_DELAY=5
FETCH_SLEEP_SEC=2
```

Save: `Ctrl+X` → `Y` → `Enter`

### Gmail App Password

Gmail requires an App Password (not your regular password) when 2FA is enabled:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable 2-Step Verification
3. Search "App passwords" → create one named "SARA"
4. Paste the 16-character password into `ALERT_SMTP_PASSWORD`

### Proxy setup (Webshare)

1. Sign up at [webshare.io](https://webshare.io) — 100 free proxies on free plan
2. Go to **Proxy List → Download → Username:Password** format
3. Convert to JSON array and paste into `WEBSHARE_PROXY_JSON`:

```env
WEBSHARE_PROXY_JSON=[["198.23.239.134","6540","user1","pass1"],["207.244.217.165","6712","user2","pass2"]]
```

Sites that automatically use proxy when configured:
`wwd_com`, `business_of_fashion`, `just_style_com`, `drapers_com`, `vogue_in`, `ajio_com`, `amazon_in`, `myntra_com`, `meesho_com`, `nykaa_fashion_com`

---

## Step 8: Enable Services

```bash
sudo systemctl enable rabbitmq-server redis-server
sudo systemctl start rabbitmq-server redis-server

# Verify
sudo systemctl status rabbitmq-server redis-server
```

---

## Step 9: Enable RabbitMQ Priority Queue

The job queue needs priority support enabled:

```bash
# The setup script does this automatically, but if running manually:
# Declare the queue via SARA (it self-declares on first use with x-max-priority: 10)
# No manual setup needed — RabbitMQ auto-creates it when scheduler or worker starts.
```

---

## Step 10: Run Setup Script

This creates all systemd services and starts everything in one shot:

```bash
bash ~/SARA/setup_server.sh
```

The script creates and starts:

| Step | Service | What it does |
|------|---------|-------------|
| 1 | — | Pins elasticsearch Python client to v8 |
| 2 | `sara-dashboard` | Streamlit dashboard on port 8501 |
| 3 | `cf-sara-dashboard`, `cf-sara-kibana`, `cf-sara-es` | Cloudflare quick tunnels |
| 4 | `sara-scheduler` | APScheduler — dispatches crawl jobs to RabbitMQ |
| 5 | `sara-worker@1` … `sara-worker@5` | 5 crawl workers that poll the job queue |
| 6 | — | Removes old cron jobs |

Each worker runs as an independent systemd service with its own log file (`logs/worker-N.log`).

---

## Step 11: Set Up Kibana

Open Kibana in your browser (Cloudflare URL printed by setup script).

1. Paste the enrollment token from:
   ```bash
   sudo /usr/share/elasticsearch/bin/elasticsearch-create-enrollment-token -s kibana
   ```
2. Paste the verification code from:
   ```bash
   sudo /usr/share/kibana/bin/kibana-verification-code
   ```
3. Log in with `elastic` / your ES password

Create data views:
- **Stack Management → Data Views → Create data view**
  - Name: `Commerce Crawl`, Index pattern: `sara-commerce-crawl`, Time field: `@timestamp`
  - Name: `Media Crawl`, Index pattern: `sara-media-crawl`, Time field: `@timestamp`

---

## Step 12: Verify Everything

```bash
# Check all services
for svc in sara-dashboard sara-scheduler sara-worker@1 sara-worker@2 sara-worker@3 sara-worker@4 sara-worker@5 elasticsearch kibana rabbitmq-server redis-server; do
    echo "$svc: $(sudo systemctl is-active $svc)"
done

# Check dashboard is responding
curl -s http://localhost:8501/_stcore/health

# Check ES is responding
curl -sk -u elastic:YOUR_PASSWORD https://localhost:9200/_cluster/health | python3 -m json.tool

# Check tunnel URLs
bash ~/SARA/show_urls.sh

# Validate all 22 sites
source venv/bin/activate
python -m tools.validate_site --all
```

---

## Step 13: Run a Test Crawl

Test the pipeline end to end before enabling schedules:

```bash
source venv/bin/activate

# Quick discovery test (no side effects, no RabbitMQ needed)
python -m tools.test_discovery media_crawl fashion_united_global_com --depth 1 --limit 5

# Full pipeline test
python crawl_runner.py media_crawl fashion_united_global_com test001

# Check output
cat logs/crawl_status.json | python -m json.tool
ls scrape_output/parser_output/media_crawl/
```

---

## Step 14: Backfill Existing Data to ES (Migration Only)

If migrating from another server with existing CSV data:

```bash
# On old server: copy parser output
rsync -avz ~/SARA/scrape_output/parser_output/ NEW_SERVER:~/SARA/scrape_output/parser_output/

# On new server: backfill to ES
cd ~/SARA && source venv/bin/activate
python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from pathlib import Path
from core.es_uploader import upload_all_existing
total = upload_all_existing(Path('.'))
print(f'Backfilled {total:,} docs to Elasticsearch')
"
```

---

## Service Management Reference

### Check status

```bash
sudo systemctl status sara-dashboard
sudo systemctl status sara-scheduler
sudo systemctl status 'sara-worker@*'
sudo systemctl status elasticsearch kibana
```

### Start / stop / restart

```bash
# All workers
for i in 1 2 3 4 5; do sudo systemctl restart sara-worker@$i; done

# Individual worker
sudo systemctl restart sara-worker@3

# Scheduler
sudo systemctl restart sara-scheduler

# Dashboard
sudo systemctl restart sara-dashboard
```

### View logs

```bash
# Dashboard
sudo journalctl -u sara-dashboard -f

# Scheduler
tail -f ~/SARA/logs/scheduler.log

# Workers (all)
tail -f ~/SARA/logs/worker-1.log &
tail -f ~/SARA/logs/worker-2.log &
# etc.

# Full pipeline log
tail -f ~/SARA/logs/pipeline.log

# Cloudflare tunnels
sudo journalctl -u cf-sara-dashboard -f
```

### Tunnel URLs (refresh after reboot)

```bash
bash ~/SARA/show_urls.sh
```

---

## Migration Checklist

When moving to a new server, complete these steps in order:

- [ ] Steps 1–10 on new server
- [ ] Copy `.env` from old server (`scp old-server:~/SARA/.env ~/SARA/.env`)
- [ ] Copy `config/schedules.json` — preserves all crawl schedules
- [ ] Copy `scrape_output/` if you want local HTML/CSV history
- [ ] Backfill ES from existing CSVs (Step 14)
- [ ] Verify dashboard loads at new Cloudflare URL
- [ ] Run a test crawl to confirm pipeline works end-to-end (`python -m tools.validate_site --all`)
- [ ] Update `README.md` Live URLs section if you use fixed public URLs

---

## Troubleshooting

### Workers not picking up jobs

```bash
# Check workers are running
sudo systemctl status 'sara-worker@*'

# Check scheduler is dispatching
tail -20 ~/SARA/logs/scheduler.log

# Inspect the job queue in RabbitMQ
sudo rabbitmqctl list_queues name messages consumers
# Should see: sara-crawl-jobs   N   5
```

### Dashboard not loading

```bash
sudo systemctl status sara-dashboard
sudo journalctl -u sara-dashboard -n 50
# Usually: missing .env variable or Python import error
```

### RabbitMQ connection refused

```bash
sudo systemctl restart rabbitmq-server
# Check CLOUDAMQP_URL in .env: amqp://guest:guest@localhost:5672/
```

### Elasticsearch SSL error

```bash
# Self-signed cert is expected for local ES — SARA handles this automatically
# Verify ELASTICSEARCH_URL starts with https://localhost:9200
curl -sk -u elastic:YOUR_PASSWORD https://localhost:9200
```

### No URLs discovered for a site

```bash
# Run discovery test to see what URLs are found
python -m tools.test_discovery media_crawl <site_name> --depth 1 --limit 10

# Common causes:
# - Wrong pagination format (WordPress vs querystring)
# - URL filter too strict
# - Site returning 403 (add proxy: webshare_proxy to the site YAML)
```

### Crawl discovers URLs but retriever gets empty HTML

```bash
# Site is likely bot-protected — add proxy to its discovery YAML:
# request_params:
#   proxy: webshare_proxy
#   timeout: 30
#   max_retries: 3

# Check if proxy is working
python -c "from proxy_config import webshare_proxy; print(len(webshare_proxy), 'proxies loaded')"
```

### Port already in use

```bash
pkill -f streamlit
sudo systemctl restart sara-dashboard
```

### ES client version mismatch

```bash
source ~/SARA/venv/bin/activate
pip install "elasticsearch>=8.0.0,<9.0.0"
```
