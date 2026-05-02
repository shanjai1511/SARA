#!/usr/bin/env bash
# Run all commerce sites sequentially to avoid RabbitMQ 20-connection limit.
# Usage: bash run_commerce_batch.sh [schedule_id]
SCHEDULE=${1:-20260426001}
cd "$(dirname "$0")"

SITES=(
  # PSS sites (existing, now with 3-depth YAML)
  meesho_com
  ajio_com
  tata_cliq_com
  max_com
  nykaa_fashion_com
  shoppersstop_com
  limeroad_com
  flipkart_com

  # Sportswear (high volume, clean HTML)
  adidas_in
  nike_com
  puma_com
  reebok_in
  under_armour_in
  asics_in
  hrx_com

  # Premium international
  tommy_hilfiger_in
  calvin_klein_in
  levis_in
  benetton_in
  vero_moda_in
  only_in
  hm_com
  marks_spencer_in
  zara_com
  superdry_in
  gap_com

  # D2C / Shopify brands
  snitch_com
  bewakoof_com
  beyoung_in
  the_souled_store_com
  bonkers_corner_com
  campus_sutra_com
  freecultr_com
  the_bear_house_com
  fablestreet_com
  damensch_com
  xyxx_com

  # Innerwear
  jockey_in
  clovia_com
  zivame_com
  pretty_secrets_com

  # Department stores / retail chains
  pantaloons_com
  lifestyle_stores_com
  westside_com
  centralandme_com
  brand_factory_com
  zudio_com
  vmart_com
  reliance_trends_com

  # Ethnic / bridal
  biba_in
  fabindia_com
  manyavar_com
  w_for_woman_com
  global_desi_in
  libas_in
  soch_com
  house_of_indya_com
  kalki_fashion_com
  aza_fashions_com
  pernia_popup_shop_com
  ritu_kumar_com
  jaypore_com
  nicobar_com
  house_of_masaba_com
  sabyasachi_com
  suta_in
  byshree_com
  nalli_com
  the_chennai_silks_com
  pothys_com
  rmkv_silks_com
  chhabra555_com
  frontier_raas_com
  andalso_in
  the_label_life_com

  # Luxury / premium
  hugo_boss_com
  armani_exchange_com
  diesel_com
  michael_kors_com
  coach_com
  luxepolis_com

  # Sustainable / artisan
  no_nasties_in
  boheco_com
  doodlage_in
  okhai_org

  # Accessories
  lenskart_com
  fastrack_in
  da_milano_com

  # Others
  koovs_com
  urbanic_com
  voonik_com
  craftsvilla_com
  dressindia_in
  ogaan_com
)

TOTAL=${#SITES[@]}
PASS=0
FAIL=0

for site in "${SITES[@]}"; do
  echo ""
  echo "──────────────────────────────────────────"
  echo "[$((PASS+FAIL+1))/$TOTAL] commerce_crawl / $site  (schedule=$SCHEDULE)"
  echo "──────────────────────────────────────────"
  python -m crawl_runner commerce_crawl "$site" "$SCHEDULE"
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
