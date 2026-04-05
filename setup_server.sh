#!/bin/bash
# SARA Server Setup Script
# Run once on the server: bash setup_server.sh
set -e

SARA_DIR="/home/shanjai/SARA"
USER="shanjai"

echo "=== SARA Server Setup ==="

# ── 1. Pin elasticsearch client version ───────────────────────────────────────
echo "[1/4] Pinning elasticsearch client version..."
source "$SARA_DIR/venv/bin/activate"
pip install -q "elasticsearch>=8.0.0,<9.0.0"
echo "Done."

# ── 2. Streamlit systemd service ──────────────────────────────────────────────
echo "[2/4] Creating Streamlit systemd service..."
sudo tee /etc/systemd/system/sara-dashboard.service > /dev/null <<EOF
[Unit]
Description=SARA Streamlit Dashboard
After=network.target elasticsearch.service rabbitmq-server.service redis-server.service

[Service]
User=$USER
WorkingDirectory=$SARA_DIR
EnvironmentFile=$SARA_DIR/.env
ExecStart=$SARA_DIR/venv/bin/streamlit run dashboard/streamlit_app.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable sara-dashboard
sudo systemctl restart sara-dashboard
echo "Done."

# ── 3. Cloudflare quick tunnel systemd services (no domain needed) ────────────
echo "[3/4] Creating Cloudflare tunnel systemd services..."

declare -A TUNNELS=(
    [sara-dashboard]="http://localhost:8501"
    [sara-kibana]="http://localhost:5601"
    [sara-es]="https://localhost:9200"
)

for NAME in "${!TUNNELS[@]}"; do
    URL="${TUNNELS[$NAME]}"
    sudo tee /etc/systemd/system/cf-${NAME}.service > /dev/null <<EOF
[Unit]
Description=Cloudflare Quick Tunnel - ${NAME}
After=network.target

[Service]
User=$USER
ExecStart=/usr/local/bin/cloudflared tunnel --url ${URL} --no-autoupdate
Restart=always
RestartSec=15
StandardOutput=append:/var/log/cf-${NAME}.log
StandardError=append:/var/log/cf-${NAME}.log

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable cf-${NAME}
    sudo systemctl restart cf-${NAME}
    echo "  Started: cf-${NAME} → ${URL}"
done
echo "Done."

# ── 4. Scheduler systemd service ──────────────────────────────────────────────
echo "[4/5] Installing APScheduler and creating scheduler service..."
source "$SARA_DIR/venv/bin/activate"
pip install -q "APScheduler>=3.10.0"

sudo tee /etc/systemd/system/sara-scheduler.service > /dev/null <<EOF
[Unit]
Description=SARA Crawl Scheduler
After=network.target sara-dashboard.service rabbitmq-server.service

[Service]
User=$USER
WorkingDirectory=$SARA_DIR
EnvironmentFile=$SARA_DIR/.env
ExecStart=$SARA_DIR/venv/bin/python -m services.scheduler.worker
Restart=always
RestartSec=15
StandardOutput=append:$SARA_DIR/logs/scheduler.log
StandardError=append:$SARA_DIR/logs/scheduler.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sara-scheduler
sudo systemctl restart sara-scheduler
echo "Done."

# ── 5. Remove old cron job (replaced by scheduler service) ────────────────────
echo "[5/5] Removing old cron job..."
crontab -l 2>/dev/null | grep -v 'crawl_runner' | crontab - || true
echo "Done."

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup Complete! Waiting 15s for tunnels to start... ==="
sleep 15

# Save URLs to a file for easy reference
URL_FILE="$SARA_DIR/tunnel_urls.txt"
echo "# SARA Tunnel URLs — generated $(date)" > "$URL_FILE"
echo "" >> "$URL_FILE"

echo ""
echo "========================================="
echo "          YOUR SARA ACCESS URLS"
echo "========================================="

declare -A LABELS=(
    [sara-dashboard]="SARA Dashboard"
    [sara-kibana]="Kibana (Data Explorer)"
    [sara-es]="Elasticsearch"
)

for NAME in sara-dashboard sara-kibana sara-es; do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cf-${NAME}.log 2>/dev/null | tail -1)
    LABEL="${LABELS[$NAME]}"
    if [ -n "$URL" ]; then
        echo "  $LABEL:"
        echo "    $URL"
        echo "$LABEL: $URL" >> "$URL_FILE"
    else
        echo "  $LABEL: still starting..."
        echo "$LABEL: run -> grep trycloudflare /var/log/cf-${NAME}.log" >> "$URL_FILE"
    fi
    echo "" >> "$URL_FILE"
done

echo "========================================="
echo ""
echo "URLs saved to: $URL_FILE"
echo "To check URLs anytime, run:  cat $URL_FILE"
echo "To refresh URLs after reboot, run:  bash $SARA_DIR/show_urls.sh"

# Create a handy show_urls script
cat > "$SARA_DIR/show_urls.sh" <<'SCRIPT'
#!/bin/bash
echo ""
echo "========================================="
echo "          YOUR SARA ACCESS URLS"
echo "========================================="
declare -A LABELS=(
    [sara-dashboard]="SARA Dashboard"
    [sara-kibana]="Kibana (Data Explorer)"
    [sara-es]="Elasticsearch"
)
for NAME in sara-dashboard sara-kibana sara-es; do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cf-${NAME}.log 2>/dev/null | tail -1)
    echo "  ${LABELS[$NAME]}: ${URL:-not running}"
done
echo "========================================="
SCRIPT
chmod +x "$SARA_DIR/show_urls.sh"
