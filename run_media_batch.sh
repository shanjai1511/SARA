#!/usr/bin/env bash
# Run all media sites sequentially to avoid RabbitMQ 20-connection limit.
# Usage: bash run_media_batch.sh [schedule_id]
SCHEDULE=${1:-20260426001}
cd "$(dirname "$0")"

SITES=(
  # Existing PSS media sites
  the_industry_fashion_com
  drapers_com
  the_fashion_law_com
  fibre_2_fashion_com
  just_style_com
  vogue_in
  fashion_united_in
  business_of_fashion
  fashion_united_global_com
  apparel_resources_com
  wwd_com

  # Trade / B2B
  vogue_business_com
  retail_dive_com
  internet_retailing_net
  retail_gazette_com
  fashion_network_com
  india_retailing_com
  et_retail_com
  glossy_com

  # Market research
  nielsen_com
  kantar_com
  redseer_com
  technopak_com
  mintel_com
  euromonitor_com

  # India business news
  economic_times_com
  business_standard_com
  financial_express_com
  livemint_com
  mint_com
  business_today_in
  hindustan_times_com
  indian_express_com
  the_hindu_com
  times_of_india_com
  scroll_in
  business_insider_in

  # India startup media
  yourstory_com
  inc42_com
  entrepreneur_com

  # India magazines
  grazia_in
  cosmopolitan_in
  elle_in
  gq_india_com
  femina_in
  harpers_bazaar_in
  lofficiel_india_com
  mans_world_india_com
  brides_today_in
  the_voice_of_fashion_com
  instyle_in

  # Global consumer fashion
  vogue_com
  elle_com
  harpers_bazaar_com
  nylon_com
  paper_mag_com
  gq_com
  popsugar_com
  who_what_wear_com
  refinery29_com
  fashionista_com
  style_caster_com
  the_trend_spotter_com

  # Streetwear / hype
  highsnobiety_com
  hypebeast_com

  # Global business / news
  forbes_com
  bloomberg_com
  fast_company_com
  vox_com
  business_insider_com
  the_guardian_com
  cnn_com
  bbc_com

  # Tech
  the_verge_com
  techcrunch_com
  wired_com

  # India local
  lbb_in
)

TOTAL=${#SITES[@]}
PASS=0
FAIL=0

for site in "${SITES[@]}"; do
  echo ""
  echo "──────────────────────────────────────────"
  echo "[$((PASS+FAIL+1))/$TOTAL] media_crawl / $site  (schedule=$SCHEDULE)"
  echo "──────────────────────────────────────────"
  python -m crawl_runner media_crawl "$site" "$SCHEDULE"
  rc=$?
  if [ $rc -eq 0 ]; then
    PASS=$((PASS+1))
    echo "✓ $site done"
  else
    FAIL=$((FAIL+1))
    echo "✗ $site FAILED (exit $rc)"
  fi
done

echo ""
echo "=============================="
echo "Batch complete: $PASS passed, $FAIL failed / $TOTAL total"
echo "=============================="
