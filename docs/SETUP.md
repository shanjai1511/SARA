# SARA Server Setup Guide

Complete step-by-step guide to deploy SARA on a fresh Ubuntu server. Follow this whenever migrating to a new machine.

---

## Prerequisites

- Ubuntu 22.04 or 24.04 (server or desktop)
- Minimum 4GB RAM, 50GB disk
- Internet access
- A GitHub account with access to the SARA repo
- A Tailscale account (free at tailscale.com)

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

## Step 5: Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Open the printed URL in your browser → sign in with your Tailscale account → authorize.

Enable Tailscale Funnel for all 3 services:
```bash
sudo tailscale funnel --bg --https=443   8501   # Dashboard
sudo tailscale funnel --bg --https=8443  5601   # Kibana
sudo tailscale funnel --bg --https=10000 9200   # Elasticsearch
```

Verify:
```bash
sudo tailscale funnel status
```

Note your permanent public URLs (format: `https://<machine>.<tailnet>.ts.net`).

---

## Step 6: Clone SARA

```bash
cd ~
git clone https://github.com/shanjai1511/SARA.git
cd SARA
```

---

## Step 7: Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install "elasticsearch>=8.0.0,<9.0.0"   # pin to ES 8.x client
```

---

## Step 8: Create `.env` File

```bash
nano ~/SARA/.env
```

Paste and fill in your values:

```env
# Required
CLOUDAMQP_URL=amqp://guest:guest@localhost:5672/
DASHBOARD_PASSWORD=your_secure_password_here
WEBSHARE_PROXY_JSON=[]

# Pipeline tuning
NUM_FETCH_WORKERS=4
NUM_PARSE_WORKERS=4
MAX_URLS=500
FETCH_DELAY=5
FETCH_SLEEP_SEC=2

# Redis (local)
REDIS_URL=redis://localhost:6379

# Elasticsearch (local)
ELASTICSEARCH_URL=https://localhost:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=your_elastic_password_here

# Alerting — email (Gmail example)
ALERT_EMAIL_TO=you@example.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=your-gmail@gmail.com
ALERT_SMTP_PASSWORD=your-gmail-app-password
# ALERT_NOTIFY_SUCCESS=true   # uncomment to also alert on success

# Alerting — Slack (optional, alternative to email)
# ALERT_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ

# SaaS (leave blank if not using)
SARA_S3_BUCKET=
SARA_API_KEY=
METRICS_PORT=8000
CORS_ORIGINS=*
```

### Gmail app password setup

Gmail requires an App Password (not your regular password) when 2FA is enabled:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable 2-Step Verification if not already on
3. Search "App passwords" → create one named "SARA"
4. Paste the 16-character password into `ALERT_SMTP_PASSWORD`

### Proxy setup (Webshare)

1. Sign up at [webshare.io](https://webshare.io) (100 free proxies on free plan)
2. Go to **Proxy List** → **Download** → select **Username:Password** format
3. Convert to JSON array format and paste into `WEBSHARE_PROXY_JSON`:

```bash
# Example format
WEBSHARE_PROXY_JSON=[["198.23.239.134","6540","user1","pass1"],["207.244.217.165","6712","user2","pass2"]]
```

Sites that auto-use proxy when configured: `wwd_com`, `business_of_fashion`, `just_style_com`
To enable proxy for any site, add to its discovery YAML:
```yaml
request_params:
  proxy: webshare_proxy
```

Save: `Ctrl+X` → `Y` → `Enter`

---

## Step 9: Enable Services

```bash
sudo systemctl enable rabbitmq-server redis-server
sudo systemctl start rabbitmq-server redis-server
```

Verify:
```bash
sudo systemctl status rabbitmq-server redis-server
```

---

## Step 10: Run Setup Script

This creates all systemd services (dashboard, scheduler, tunnels) and sets up auto-start on reboot:

```bash
bash ~/SARA/setup_server.sh
```

The script will:
1. Pin elasticsearch Python client to v8
2. Create `sara-dashboard` systemd service (Streamlit on port 8501)
3. Create Cloudflare quick tunnel systemd services for dashboard, Kibana, ES
4. Create `sara-scheduler` systemd service (APScheduler)
5. Remove old cron jobs (replaced by scheduler)

---

## Step 11: Set Up Kibana

Open Kibana in your browser at `https://<your-tailscale-url>:8443`

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
- Go to **Stack Management → Data Views → Create data view**
- Name: `Commerce Crawl`, Index pattern: `sara-commerce-crawl`, Time field: `@timestamp`
- Name: `Media Crawl`, Index pattern: `sara-media-crawl`, Time field: `@timestamp`

---

## Step 12: Verify Everything

```bash
# Check all services
for svc in sara-dashboard sara-scheduler elasticsearch kibana rabbitmq-server redis-server; do
    echo "$svc: $(sudo systemctl is-active $svc)"
done

# Check dashboard is responding
curl -s http://localhost:8501/_stcore/health

# Check ES is responding
curl -sk -u elastic:YOUR_PASSWORD https://localhost:9200/_cluster/health | python3 -m json.tool

# Check tunnel URLs
bash ~/SARA/show_urls.sh
```

---

## Step 13: Backfill Existing Data to ES (Migration Only)

If migrating from another server with existing CSV data, copy the CSV files first, then backfill:

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
sudo systemctl status elasticsearch
sudo systemctl status kibana
```

### Restart services
```bash
sudo systemctl restart sara-dashboard
sudo systemctl restart sara-scheduler
sudo systemctl restart elasticsearch kibana
sudo systemctl restart rabbitmq-server redis-server
```

### View logs
```bash
# Dashboard
sudo journalctl -u sara-dashboard -f

# Scheduler
tail -f ~/SARA/logs/scheduler.log

# Pipeline
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

- [ ] Steps 1–10 above on new server
- [ ] Copy `.env` from old server
- [ ] Copy `config/schedules.json` (preserves crawl schedules)
- [ ] Copy `scrape_output/` if you want local HTML/CSV history
- [ ] Backfill ES from existing CSVs (Step 13)
- [ ] Update Tailscale Funnel and note new public URLs
- [ ] Update `README.md` Live URLs section with new Tailscale hostname
- [ ] Verify dashboard loads at new URL
- [ ] Run a test crawl to confirm pipeline works end-to-end

---

## Troubleshooting

### Dashboard not loading
```bash
sudo systemctl status sara-dashboard
sudo journalctl -u sara-dashboard -n 50
# Usually: missing .env variable or Python import error
```

### RabbitMQ connection refused
```bash
sudo systemctl restart rabbitmq-server
# Check CLOUDAMQP_URL in .env matches local: amqp://guest:guest@localhost:5672/
```

### Elasticsearch SSL error
```bash
# Self-signed cert is expected for local ES — SARA handles this automatically
# Verify ELASTICSEARCH_URL starts with https://localhost
```

### Tailscale Funnel URL not working
```bash
sudo tailscale funnel status
# If empty, re-run:
sudo tailscale funnel --bg --https=443   8501
sudo tailscale funnel --bg --https=8443  5601
sudo tailscale funnel --bg --https=10000 9200
```

### Port already in use
```bash
# Kill existing streamlit process
pkill -f streamlit
sudo systemctl restart sara-dashboard
```

### ES client version mismatch
```bash
# Ensure ES Python client matches server version (8.x)
source ~/SARA/venv/bin/activate
pip install "elasticsearch>=8.0.0,<9.0.0"
```
