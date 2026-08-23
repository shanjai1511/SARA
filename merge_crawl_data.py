"""
merge_crawl_data.py — combine every per-site parser CSV for a schedule into
one CSV per project (media_crawl, commerce_crawl).

Site YAML configs each declare their own field set, so the merged CSV's
header is the union of every site's columns (first-seen order), with a
`site_name` column added — same convention core/es_uploader.py already uses
when it indexes multiple sites into one ES index.

Usage:
    python merge_crawl_data.py [schedule_id]

    schedule_id defaults to "direct" + today's date (the direct-crawl batch's
    convention) if omitted.
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))   # some sites embed long body text in a field


def merge_project(project: str, schedule_id: str) -> Path | None:
    parser_output = BASE_DIR / "scrape_output" / "parser_output" / project
    csv_paths = sorted(parser_output.glob(f"*_{schedule_id}/*.csv"))
    if not csv_paths:
        print(f"{project}: no CSVs found for schedule_id={schedule_id}")
        return None

    fieldnames = ["site_name", "schedule_id"]
    seen = set(fieldnames)
    for p in csv_paths:
        with open(p, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for fn in reader.fieldnames or []:
                if fn not in seen:
                    seen.add(fn)
                    fieldnames.append(fn)

    out_dir = BASE_DIR / "scrape_output" / "merged_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{project}_{schedule_id}_merged.csv"

    total_rows = 0
    with open(out_path, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for p in csv_paths:
            schedule_dir = p.parent.name   # {site}_{project}_{schedule_id}
            site_name = schedule_dir.replace(f"_{project}_{schedule_id}", "")
            with open(p, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["site_name"]    = site_name
                    row["schedule_id"]  = schedule_id
                    writer.writerow(row)
                    total_rows += 1

    print(f"{project}: merged {len(csv_paths)} site CSVs, {total_rows} rows -> {out_path}")
    return out_path


def main() -> None:
    schedule_id = sys.argv[1] if len(sys.argv) > 1 else "direct" + time.strftime("%Y%m%d")
    for project in ("media_crawl", "commerce_crawl"):
        merge_project(project, schedule_id)


if __name__ == "__main__":
    main()
