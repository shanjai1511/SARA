#!/bin/bash
# SARA Server Setup Script
# Run once on the server: bash setup_server.sh
set -e

SARA_DIR="/home/shanjai/SARA"
USER="shanjai"
CF_DIR="/home/shanjai/.cloudflared"

echo "=== SARA Server Setup ==="

# ── 1. Pin elasticsearch client version ───────────────────────────────────────
echo "[1/5] Pinning elasticsearch client version..."
source "$SARA_DIR/venv/bin/activate"
pip install -q "elasticsearch>=8.0.0,<9.0.0"
echo "Done."

# ── 2. Streamlit systemd service ──────────────────────────────────────────────
echo "[2/5] Creating Streamlit systemd service..."
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

# ── 3. Permanent Cloudflare tunnels ───────────────────────────────────────────
echo "[3/5] Setting up permanent Cloudflare tunnels..."

# Check if already logged in
if [ ! -f "$CF_DIR/cert.pem" ]; then
    echo ""
    echo ">>> ACTION REQUIRED: Login to Cloudflare (browser will open)"
    cloudflared tunnel login
fi

# Create tunnels (skip if already exist)
for TUNNEL in sara-dashboard sara-kibana sara-es; do
    if ! cloudflared tunnel list | grep -q "$TUNNEL"; then
        cloudflared tunnel create "$TUNNEL"
        echo "Created tunnel: $TUNNEL"
    else
        echo "Tunnel already exists: $TUNNEL"
    fi
done

# Get tunnel UUIDs
DASHBOARD_UUID=$(cloudflared tunnel list | grep sara-dashboard | awk '{print $1}')
KIBANA_UUID=$(cloudflared tunnel list | grep sara-kibana | awk '{print $1}')
ES_UUID=$(cloudflared tunnel list | grep sara-es | awk '{print $1}')

# Write tunnel config files
mkdir -p "$CF_DIR"

cat > "$CF_DIR/sara-dashboard.yml" <<EOF
tunnel: $DASHBOARD_UUID
credentials-file: $CF_DIR/$DASHBOARD_UUID.json
ingress:
  - service: http://localhost:8501
EOF

cat > "$CF_DIR/sara-kibana.yml" <<EOF
tunnel: $KIBANA_UUID
credentials-file: $CF_DIR/$KIBANA_UUID.json
ingress:
  - service: http://localhost:5601
EOF

cat > "$CF_DIR/sara-es.yml" <<EOF
tunnel: $ES_UUID
credentials-file: $CF_DIR/$ES_UUID.json
ingress:
  - service: https://localhost:9200
    originRequest:
      noTLSVerify: true
EOF

# ── 4. Systemd services for each tunnel ───────────────────────────────────────
echo "[4/5] Creating tunnel systemd services..."

for TUNNEL in sara-dashboard sara-kibana sara-es; do
    sudo tee /etc/systemd/system/cf-${TUNNEL}.service > /dev/null <<EOF
[Unit]
Description=Cloudflare Tunnel - ${TUNNEL}
After=network.target

[Service]
User=$USER
ExecStart=/usr/local/bin/cloudflared tunnel --config $CF_DIR/${TUNNEL}.yml run
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable cf-${TUNNEL}
    sudo systemctl restart cf-${TUNNEL}
done
echo "Done."

# ── 5. Cron schedule for crawls (runs daily at 2 AM) ─────────────────────────
echo "[5/5] Setting up daily crawl cron job..."
(crontab -l 2>/dev/null | grep -v 'crawl_runner'; echo "0 2 * * * cd $SARA_DIR && $SARA_DIR/venv/bin/python crawl_runner.py >> $SARA_DIR/logs/cron.log 2>&1") | crontab -
echo "Done."

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Your permanent tunnel URLs:"
echo "  Dashboard : https://${DASHBOARD_UUID}.cfargotunnel.com"
echo "  Kibana    : https://${KIBANA_UUID}.cfargotunnel.com"
echo "  ES        : https://${ES_UUID}.cfargotunnel.com"
echo ""
echo "Services status:"
sudo systemctl is-active sara-dashboard cf-sara-dashboard cf-sara-kibana cf-sara-es 2>/dev/null || true
