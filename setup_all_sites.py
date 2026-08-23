"""
Scaffold all new commerce sites that are not yet in SARA.
Run: python setup_all_sites.py
"""
import sys
from pathlib import Path
from creation_script import main as scaffold

NEW_COMMERCE_SITES = [
    # International fast fashion
    "hm_com",
    "marks_spencer_in",
    "zara_com",
    "gap_com",
    "superdry_in",
    # Online-only / Gen-Z
    "koovs_com",
    "urbanic_com",
    "bewakoof_com",
    "beyoung_in",
    "fablestreet_com",
    "bonkers_corner_com",
    "snitch_com",
    "the_bear_house_com",
    "campus_sutra_com",
    "the_souled_store_com",
    "freecultr_com",
    # Department stores / retail chains
    "lifestyle_stores_com",
    "westside_com",
    "centralandme_com",
    "pantaloons_com",
    "brand_factory_com",
    "vmart_com",
    "zudio_com",
    "reliance_trends_com",
    # Ethnic & bridal
    "the_chennai_silks_com",
    "pothys_com",
    "rmkv_silks_com",
    "nalli_com",
    "kalki_fashion_com",
    "chhabra555_com",
    "frontier_raas_com",
    "biba_in",
    "w_for_woman_com",
    "global_desi_in",
    "manyavar_com",
    "fabindia_com",
    "suta_in",
    "soch_com",
    "libas_in",
    "dressindia_in",
    "byshree_com",
    "craftsvilla_com",
    "voonik_com",
    # Designer / luxury
    "aza_fashions_com",
    "pernia_popup_shop_com",
    "ogaan_com",
    "luxepolis_com",
    "ritu_kumar_com",
    "sabyasachi_com",
    "house_of_masaba_com",
    "jaypore_com",
    "nicobar_com",
    "the_label_life_com",
    "andalso_in",
    # Fusion / contemporary ethnic
    "house_of_indya_com",
    # Sportswear
    "nike_com",
    "adidas_in",
    "puma_com",
    "reebok_in",
    "under_armour_in",
    "asics_in",
    "hrx_com",
    # Premium international brands
    "tommy_hilfiger_in",
    "calvin_klein_in",
    "levis_in",
    "benetton_in",
    "vero_moda_in",
    "only_in",
    "armani_exchange_com",
    "hugo_boss_com",
    "diesel_com",
    "michael_kors_com",
    "coach_com",
    # Innerwear
    "jockey_in",
    "damensch_com",
    "xyxx_com",
    "clovia_com",
    "zivame_com",
    "pretty_secrets_com",
    # Accessories
    "lenskart_com",
    "fastrack_in",
    "da_milano_com",
    # Sustainable / artisan
    "no_nasties_in",
    "boheco_com",
    "doodlage_in",
    "okhai_org",
]

if __name__ == "__main__":
    project = "commerce_crawl"
    created = 0
    failed = []

    for site in NEW_COMMERCE_SITES:
        try:
            scaffold([project, site])
            created += 1
        except Exception as e:
            print(f"ERROR scaffolding {site}: {e}", file=sys.stderr)
            failed.append(site)

    print(f"\nDone: {created}/{len(NEW_COMMERCE_SITES)} sites scaffolded.")
    if failed:
        print(f"Failed: {failed}")
