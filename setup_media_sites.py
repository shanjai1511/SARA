"""
Scaffold all new media crawl sites not yet in SARA.
Run: python setup_media_sites.py
"""
import sys
from creation_script import main as scaffold

NEW_MEDIA_SITES = [
    # ── Trade publications (new) ──────────────────────────────────────────
    "vogue_business_com",       # voguebusiness.com  — "AI Code done" in sheet but missing from SARA
    "retail_dive_com",          # retaildive.com
    "internet_retailing_net",   # internetretailing.net
    "retail_gazette_com",       # retailgazette.co.uk
    "fashion_network_com",      # fashionnetwork.com
    "india_retailing_com",      # indiaretailing.com
    "et_retail_com",            # etretail.com
    "glossy_com",               # glossy.co

    # ── Market research & consulting ──────────────────────────────────────
    "nielsen_com",              # nielsen.com
    "kantar_com",               # kantar.com
    "redseer_com",              # redseer.com
    "technopak_com",            # technopak.com
    "mintel_com",               # mintel.com
    "euromonitor_com",          # euromonitor.com

    # ── India business news ───────────────────────────────────────────────
    "economic_times_com",       # economictimes.indiatimes.com
    "business_standard_com",    # business-standard.com
    "financial_express_com",    # financialexpress.com
    "livemint_com",             # livemint.com
    "business_today_in",        # businesstoday.in
    "hindustan_times_com",      # hindustantimes.com
    "indian_express_com",       # indianexpress.com
    "the_hindu_com",            # thehindu.com
    "times_of_india_com",       # timesofindia.indiatimes.com
    "scroll_in",                # scroll.in
    "business_insider_in",      # businessinsider.in
    "mint_com",                 # livemint.com (alias)

    # ── India startup media ───────────────────────────────────────────────
    "yourstory_com",            # yourstory.com
    "inc42_com",                # inc42.com
    "entrepreneur_com",         # entrepreneur.com

    # ── India fashion magazines ───────────────────────────────────────────
    "grazia_in",                # grazia.co.in
    "cosmopolitan_in",          # cosmopolitan.in
    "elle_in",                  # elle.in
    "gq_india_com",             # gqindia.com
    "femina_in",                # femina.in
    "harpers_bazaar_in",        # harpersbazaar.in
    "lofficiel_india_com",      # lofficielindia.com
    "mans_world_india_com",     # mansworldindia.com
    "brides_today_in",          # bridestoday.in
    "the_voice_of_fashion_com", # thevoiceoffashion.com
    "instyle_in",               # instyle.co.in

    # ── Global fashion magazines ──────────────────────────────────────────
    "vogue_com",                # vogue.com
    "elle_com",                 # elle.com
    "harpers_bazaar_com",       # harpersbazaar.com
    "nylon_com",                # nylon.com
    "paper_mag_com",            # papermag.com
    "gq_com",                   # gq.com

    # ── Consumer fashion sites ────────────────────────────────────────────
    "popsugar_com",             # popsugar.com
    "who_what_wear_com",        # whowhatwear.com
    "refinery29_com",           # refinery29.com
    "fashionista_com",          # fashionista.com
    "style_caster_com",         # stylecaster.com
    "the_trend_spotter_com",    # trendspotter.net

    # ── Streetwear / culture ──────────────────────────────────────────────
    "highsnobiety_com",         # highsnobiety.com
    "hypebeast_com",            # hypebeast.com

    # ── Global business press ─────────────────────────────────────────────
    "forbes_com",               # forbes.com
    "bloomberg_com",            # bloomberg.com
    "fast_company_com",         # fastcompany.com
    "vox_com",                  # vox.com
    "business_insider_com",     # businessinsider.com

    # ── Global news ───────────────────────────────────────────────────────
    "the_guardian_com",         # theguardian.com
    "cnn_com",                  # cnn.com
    "bbc_com",                  # bbc.com

    # ── Tech / commerce tech ──────────────────────────────────────────────
    "the_verge_com",            # theverge.com
    "techcrunch_com",           # techcrunch.com
    "wired_com",                # wired.com

    # ── India local / discovery ───────────────────────────────────────────
    "lbb_in",                   # lbb.in
]

if __name__ == "__main__":
    project = "media_crawl"
    created = 0
    failed = []

    for site in NEW_MEDIA_SITES:
        try:
            scaffold([project, site])
            created += 1
        except Exception as e:
            print(f"ERROR scaffolding {site}: {e}", file=sys.stderr)
            failed.append(site)

    print(f"\nDone: {created}/{len(NEW_MEDIA_SITES)} media sites scaffolded.")
    if failed:
        print(f"Failed: {failed}")
