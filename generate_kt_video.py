"""
generate_kt_video.py  —  Creates a KT (Knowledge Transfer) video for the SARA pipeline.

Requirements:
    pip install Pillow gTTS moviepy

    Windows: also install ffmpeg and add to PATH
        https://www.gyan.dev/ffmpeg/builds/  (download ffmpeg-release-essentials.zip)
        Extract and add the bin/ folder to your system PATH.

Usage:
    python generate_kt_video.py
    python generate_kt_video.py --output my_video.mp4
"""

import os
import sys
import textwrap
import argparse
import tempfile
from pathlib import Path

# ── Dependency checks ─────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("ERROR: pip install Pillow")

try:
    from gtts import gTTS
except ImportError:
    sys.exit("ERROR: pip install gTTS")

try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    def _set_duration(clip, d): return clip.set_duration(d)
    def _set_audio(clip, a):    return clip.set_audio(a)
except ImportError:
    try:
        from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
        def _set_duration(clip, d): return clip.with_duration(d)
        def _set_audio(clip, a):    return clip.with_audio(a)
    except ImportError:
        sys.exit("ERROR: pip install moviepy")


# ── Layout constants ──────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 720
FPS           = 24
AUDIO_PADDING = 0.6   # seconds of silence after each narration

BG           = (13, 17, 38)
PANEL_BG     = (22, 28, 58)
ACCENT       = (56, 189, 248)
WHITE        = (255, 255, 255)
LIGHT_GRAY   = (210, 215, 235)
MUTED        = (130, 145, 180)
BULLET_DOT   = (56, 189, 248)
FOOTER_BG    = (18, 22, 48)
SUCCESS      = (74, 222, 128)
WARNING      = (251, 191, 36)


# ── Slide definitions ─────────────────────────────────────────────────────────
SLIDES = [
    {
        "type": "title",
        "title": "SARA Pipeline",
        "subtitle": "Knowledge Transfer",
        "caption": "Scalable Automated Retail Analytics",
        "narration": (
            "Welcome to the SARA pipeline knowledge transfer. "
            "SARA stands for Scalable Automated Retail Analytics. "
            "In this session we will walk through the system architecture, "
            "how the crawlers work, and how to operate and extend the platform."
        ),
    },
    {
        "type": "content",
        "title": "What is SARA?",
        "bullets": [
            "Crawls 170+ Indian and global fashion & retail websites",
            "Two crawler types: Commerce (products) and Media (articles)",
            "Discovers URLs → Fetches pages → Parses structured data",
            "Powers pricing intelligence, trend tracking, and analytics",
            "Runs scheduled batches with a single command",
        ],
        "narration": (
            "SARA is a scalable automated retail analytics platform. "
            "It crawls over 170 fashion and retail websites, "
            "split into two types: commerce crawlers that find product URLs, "
            "and media crawlers that find article URLs. "
            "Data flows through three stages: URL discovery, page fetching, and parsing. "
            "The output powers pricing intelligence, trend tracking, and competitive analytics."
        ),
    },
    {
        "type": "content",
        "title": "System Architecture",
        "bullets": [
            "Stage 1 — URL Discovery: category pages → product/article URLs",
            "Stage 2 — RabbitMQ: discovered URLs queued for retrieval",
            "Stage 3 — URL Retriever: fetches each page via proxy",
            "Stage 4 — Parser: extracts structured fields from HTML",
            "crawl_runner.py orchestrates all four stages end-to-end",
            "Sequential batch execution respects RabbitMQ 20-connection limit",
        ],
        "narration": (
            "The pipeline has four stages. "
            "URL Discovery crawls category listing pages to find product or article URLs. "
            "These URLs are pushed into RabbitMQ as a queue. "
            "The URL Retriever picks them up and fetches each page through a proxy. "
            "The Parser extracts structured fields like name, price, and category. "
            "The crawl runner dot py file orchestrates all stages together. "
            "Batches always run sequentially to stay within the 20-connection RabbitMQ limit."
        ),
    },
    {
        "type": "content",
        "title": "Project Structure",
        "bullets": [
            "url_discovery/commerce_crawl/  — per-site .py + .yml  (94 sites)",
            "url_discovery/media_crawl/     — per-site .py + .yml  (77 sites)",
            "url_retriever/                 — page fetchers",
            "sdf_module/url_discovery.py    — core depth-crawl engine",
            "core/discovery_helpers.py      — shopify_pages, querystring_pages, wordpress_pages",
            "run_commerce_batch.sh          — run all 94 commerce sites sequentially",
            "run_media_batch.sh             — run all 77 media sites sequentially",
        ],
        "narration": (
            "The project is organized by crawler type. "
            "Each site has exactly two files: a YAML for configuration and a Python class for logic. "
            "Commerce and media crawlers live in separate subfolders. "
            "The sdf module contains the core depth-crawl engine. "
            "The discovery helpers module provides pagination helpers like shopify pages, "
            "querystring pages, and wordpress pages. "
            "The two batch shell scripts run all sites sequentially with one command."
        ),
    },
    {
        "type": "content",
        "title": "3-Depth YAML — How Volume is Generated",
        "bullets": [
            "depth0 → seed_url list  (e.g. men-tshirts, women-tops, jeans)",
            "depth1 → get_pagination_url  (generates page 1 through 20)",
            "depth2 → get_product_url     (extracts product links from each page)",
            "Example: 10 seeds × 20 pages = 200 listing pages crawled",
            "request_params: proxy, timeout 30s, max_retries 3",
        ],
        "narration": (
            "Each YAML defines three depths that control crawl volume. "
            "Depth zero holds seed URLs — category pages like mens t-shirts or womens dresses. "
            "Depth one calls get pagination URL which generates up to 20 pages per seed. "
            "Depth two calls get product URL to extract individual product links from each listing page. "
            "With 10 seed URLs and 20 pages each, the crawler visits 200 listing pages per site. "
            "Request parameters set the proxy, timeout, and retry policy."
        ),
    },
    {
        "type": "content",
        "title": "Commerce Crawl — Three Patterns",
        "bullets": [
            "Pattern A — Shopify (~30 D2C brands: Snitch, Bewakoof, The Souled Store)",
            "  shopify_pages(keyurl, count=20)  →  ?page=1..20",
            "  XPath: //a[contains(@href, '/products/')]",
            "Pattern B — Standard querystring (~56 sites: Tommy Hilfiger, Adidas, Zara)",
            "  querystring_pages(keyurl, param='page', start=1, count=20)",
            "  PRODUCT_PATTERNS = ['/product/', '/p/', '/dp/']",
            "Pattern C — Custom PSS (11 sites: Myntra, Amazon, Ajio, Flipkart)",
            "  Complex custom Python — never overwritten, only YAML updated",
        ],
        "narration": (
            "Commerce sites fall into three patterns. "
            "Pattern A covers about 30 direct-to-consumer Shopify brands. "
            "These use the shopify pages helper which appends page equals 1 through 20. "
            "Product URLs always contain slash products slash. "
            "Pattern B covers 56 standard sites that use querystring pagination. "
            "These define product patterns to identify product detail page URLs. "
            "Pattern C covers 11 protected PSS sites like Myntra, Amazon, and Ajio "
            "which have complex custom Python for API calls, JavaScript state parsing, and DOM detection. "
            "These Python files are never overwritten — only their YAMLs are updated."
        ),
    },
    {
        "type": "content",
        "title": "Media Crawl",
        "bullets": [
            "77 sources: trade, magazines, India business news, market research",
            "WordPress sites  → wordpress_pages(keyurl, count=15)",
            "Standard sites   → querystring_pages(keyurl, param='page', count=15)",
            "Article detection: ARTICLE_PATHS + SKIP_SEGMENTS filter",
            "Skips: tag, author, category, feed, search, video, gallery pages",
            "Requires ≥ 2 URL path segments to qualify as an article",
        ],
        "narration": (
            "The media crawl covers 77 sources split across trade publications, "
            "consumer magazines, Indian business news sites, and market research firms. "
            "WordPress sites use the wordpress pages helper. "
            "Standard sites use querystring pagination. "
            "Article detection filters out non-article pages using a skip segments list "
            "that excludes tags, authors, category indexes, feeds, and search results. "
            "A URL must have at least two path segments to qualify as a real article."
        ),
    },
    {
        "type": "content",
        "title": "Adding a New Site",
        "bullets": [
            "Step 1 — Scaffold:  python creation_script.py commerce_crawl new_site_com",
            "Step 2 — Edit YAML: add real seed URLs (t-shirts, tops, dresses first)",
            "Step 3 — Edit .py:  implement get_pagination_url + get_product_url",
            "          Shopify?  use shopify_pages()      →  /products/ xpath",
            "          Standard? use querystring_pages()  →  PRODUCT_PATTERNS",
            "Step 4 — Add to:    run_commerce_batch.sh  (site name only, no extension)",
            "Step 5 — Test:      python -m crawl_runner commerce_crawl new_site_com 20260426001",
        ],
        "narration": (
            "To add a new site, follow five steps. "
            "First, run creation script dot py with the project type and site name to generate the stub files. "
            "Second, edit the YAML to add real seed URLs, prioritizing t-shirt and top category pages. "
            "Third, edit the Python file to implement get pagination URL and get product URL. "
            "Choose shopify pages for Shopify brands or querystring pages for standard sites. "
            "Fourth, add the site name to the batch script. "
            "Fifth, test it with crawl runner before committing to production batches."
        ),
    },
    {
        "type": "content",
        "title": "Running the Crawls",
        "bullets": [
            "Commerce:  bash run_commerce_batch.sh 20260426001",
            "Media:     bash run_media_batch.sh    20260426001",
            "Schedule ID format: YYYYMMDD + 3-digit sequence (e.g. 20260426001)",
            "Logs: logs/commerce_batch_YYYYMMDD.log",
            "Monitor:   tail -f logs/commerce_batch_20260426.log",
            "Never run sites in parallel — always use the batch scripts",
        ],
        "narration": (
            "Run the commerce batch with bash run commerce batch dot sh followed by the schedule ID. "
            "The schedule ID is the date plus a three-digit sequence number. "
            "Media runs the same way with run media batch dot sh. "
            "Logs go to the logs folder with the date in the filename. "
            "Use tail -f on the log file to monitor progress in real time. "
            "Always use the batch scripts — never start multiple crawlers in parallel "
            "as this exceeds the RabbitMQ connection limit."
        ),
    },
    {
        "type": "content",
        "title": "Debugging & Common Issues",
        "bullets": [
            "✗ FAILED exit 1       → read the traceback in the log file",
            "0 records crawled     → wrong YAML depth OR missing/dead seed URLs",
            "max_workers = 0       → pagination returned empty list (proxy block)",
            "RabbitMQ errors       → too many parallel crawlers — use batch script",
            "403 / bot protection  → site needs residential proxy upgrade",
            "ImportError on site   → class name mismatch — check normalize_class_name()",
        ],
        "narration": (
            "Here are the most common issues and how to fix them. "
            "A FAILED exit one means check the full traceback in the log file. "
            "Zero records usually means the YAML has wrong depth or the seed URLs are dead. "
            "A max workers equals zero error means pagination returned empty, usually a proxy block. "
            "RabbitMQ connection errors happen when crawlers run in parallel — always use the batch script. "
            "A 403 or bot protection error means the site needs a residential proxy. "
            "An import error usually means the Python class name doesn't match what normalize class name generates."
        ),
    },
    {
        "type": "content",
        "title": "Key Helper Functions",
        "bullets": [
            "shopify_pages(url, count=20)         → list of ?page=1..N URLs",
            "querystring_pages(url, param, count) → list of ?param=1..N URLs",
            "wordpress_pages(url, count=15)       → list of /page/2/../N/ URLs",
            "sdfFetch.get_page_content_hash(url)  → {status_code, page_doc}",
            "html.fromstring(page_doc)            → lxml parsed tree for XPath",
            "urljoin(base, href)                  → resolves relative URLs",
        ],
        "narration": (
            "These are the key helper functions you will use when writing crawlers. "
            "shopify pages generates Shopify pagination URLs. "
            "querystring pages generates standard query string pagination. "
            "wordpress pages generates WordPress slash page slash N slash URLs. "
            "sdf Fetch dot get page content hash fetches a URL and returns a dict with status code and page document. "
            "html dot fromstring parses the HTML into an lxml tree for XPath queries. "
            "urljoin resolves relative href values into absolute URLs."
        ),
    },
    {
        "type": "summary",
        "title": "Summary",
        "bullets": [
            "171 sites total — 94 commerce + 77 media",
            "3-depth YAML drives all crawl volume (seed → paginate → extract)",
            "Three commerce patterns: Shopify / Standard QS / Custom PSS",
            "Always use batch scripts — sequential, never parallel",
            "creation_script.py scaffolds new sites in seconds",
            "Logs tell the full story — always check them on failures",
        ],
        "narration": (
            "To summarize: SARA covers 171 sites across commerce and media. "
            "The three-depth YAML is the engine behind all crawl volume. "
            "Commerce sites follow one of three patterns: Shopify, standard querystring, or custom PSS. "
            "Always run batches sequentially. "
            "Use creation script to scaffold new sites in seconds. "
            "And always read the logs — they contain the full traceback for any failure. "
            "Thank you for watching this knowledge transfer for the SARA pipeline."
        ),
    },
]


# ── Font loader ───────────────────────────────────────────────────────────────
_FONT_CACHE: dict = {}

def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = (
        [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold else
        [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    font = None
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# ── Slide renderers ───────────────────────────────────────────────────────────
def _footer(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle([(0, HEIGHT - 38), (WIDTH, HEIGHT)], fill=FOOTER_BG)
    draw.rectangle([(0, HEIGHT - 39), (WIDTH, HEIGHT - 38)], fill=ACCENT)
    draw.text(
        (WIDTH // 2, HEIGHT - 19),
        "SARA Pipeline  ·  Scalable Automated Retail Analytics  ·  KT",
        font=load_font(15),
        fill=MUTED,
        anchor="mm",
    )


def render_title_slide(slide: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Top accent stripe
    draw.rectangle([(0, 0), (WIDTH, 6)], fill=ACCENT)

    # Centered glow panel
    px, py, pw, ph = 160, 180, WIDTH - 320, 320
    draw.rounded_rectangle([(px, py), (px + pw, py + ph)], radius=18, fill=PANEL_BG)
    draw.rounded_rectangle([(px, py), (px + pw, py + ph)], radius=18, outline=ACCENT, width=2)

    cx = WIDTH // 2
    draw.text((cx, py + 80), slide["title"], font=load_font(72, bold=True), fill=WHITE, anchor="mm")
    draw.rectangle([(cx - 180, py + 110), (cx + 180, py + 113)], fill=ACCENT)
    draw.text((cx, py + 150), slide["subtitle"], font=load_font(34), fill=ACCENT, anchor="mm")
    draw.text((cx, py + 205), slide["caption"], font=load_font(22), fill=MUTED, anchor="mm")

    _footer(draw)
    return img


def render_content_slide(slide: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (WIDTH, 6)], fill=ACCENT)

    # Title area background
    draw.rectangle([(0, 6), (WIDTH, 100)], fill=PANEL_BG)
    draw.text((60, 52), slide["title"], font=load_font(40, bold=True), fill=ACCENT, anchor="lm")
    draw.rectangle([(0, 100), (WIDTH, 104)], fill=ACCENT)

    y = 128
    for bullet in slide.get("bullets", []):
        indent = bullet.startswith("  ")
        text = bullet.lstrip()

        if indent:
            dot_x, dot_r, text_x, dot_color, font_size = 100, 5, 118, MUTED, 22
        else:
            dot_x, dot_r, text_x, dot_color, font_size = 68, 7, 90, BULLET_DOT, 26

        # Wrap text
        wrap_width = 88 if not indent else 92
        lines = textwrap.wrap(text, width=wrap_width)
        if not lines:
            y += 10
            continue

        # Dot aligned to first line
        mid_y = y + font_size // 2
        draw.ellipse([(dot_x - dot_r, mid_y - dot_r), (dot_x + dot_r, mid_y + dot_r)], fill=dot_color)

        color = LIGHT_GRAY if not indent else MUTED
        for line in lines:
            draw.text((text_x, y), line, font=load_font(font_size), fill=color)
            y += font_size + 6
        y += 10 if not indent else 4

    _footer(draw)
    return img


def render_summary_slide(slide: dict) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (WIDTH, 6)], fill=SUCCESS)

    draw.rectangle([(0, 6), (WIDTH, 100)], fill=PANEL_BG)
    draw.text((60, 52), slide["title"], font=load_font(40, bold=True), fill=SUCCESS, anchor="lm")
    draw.rectangle([(0, 100), (WIDTH, 104)], fill=SUCCESS)

    y = 128
    for bullet in slide.get("bullets", []):
        lines = textwrap.wrap(bullet, width=85)
        if not lines:
            y += 10
            continue
        draw.ellipse([(68, y + 9), (80, y + 21)], fill=SUCCESS)
        for line in lines:
            draw.text((92, y), line, font=load_font(26), fill=LIGHT_GRAY)
            y += 32
        y += 8

    _footer(draw)
    return img


def render_slide(slide: dict) -> Image.Image:
    t = slide.get("type", "content")
    if t == "title":
        return render_title_slide(slide)
    if t == "summary":
        return render_summary_slide(slide)
    return render_content_slide(slide)


# ── Main ──────────────────────────────────────────────────────────────────────
def main(output_file: str = "sara_kt_video.mp4") -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="sara_kt_"))
    print(f"Temp directory: {tmp_dir}")
    print(f"Generating {len(SLIDES)} slides...\n")

    clips = []

    for i, slide in enumerate(SLIDES):
        label = f"[{i+1:02d}/{len(SLIDES)}] {slide['title']}"
        print(f"  {label}")

        # Render slide image
        img_path = tmp_dir / f"slide_{i:02d}.png"
        render_slide(slide).save(img_path)

        # Generate TTS audio
        audio_path = tmp_dir / f"audio_{i:02d}.mp3"
        gTTS(text=slide["narration"], lang="en", slow=False).save(str(audio_path))

        # Build clip: image duration = audio duration + padding
        audio_clip = AudioFileClip(str(audio_path))
        duration = audio_clip.duration + AUDIO_PADDING
        video_clip = _set_audio(_set_duration(ImageClip(str(img_path)), duration), audio_clip)
        clips.append(video_clip)

    print(f"\nConcatenating {len(clips)} clips -> {output_file} ...")
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(
        output_file,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        logger="bar",
    )
    print(f"\nDone!  Video saved to: {Path(output_file).resolve()}")
    print(f"Duration: ~{final.duration:.0f} seconds ({final.duration/60:.1f} minutes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate SARA KT video")
    parser.add_argument("--output", default="sara_kt_video.mp4", help="Output MP4 filename")
    args = parser.parse_args()
    main(output_file=args.output)
