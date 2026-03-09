# open-medium 🪞📄

Tools to discover Medium article URLs for a user and download full PDFs via the Freedium mirror pipeline. ✨

## What’s Included 🧰

- `medium_user_range_scraper.py`: End-to-end script that discovers a user’s articles in a date range and downloads PDFs.
- `scraper_v3.py`: Mirror-based fetch + validation + PDF rendering pipeline.
- `MEDIUM_USER_RANGE_SCRAPER_USAGE.md`: Detailed usage guide.
- `SCRAPER_V3_REPLICATION_SPEC.md`: Replication spec and debugging history.

## Quick Start ⚡

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the end-to-end scraper:

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-02-01 \
  --end-date 2026-03-09 \
  --output-dir agent_native_articles_range \
  --save-url-list
```

## Recommended Local Tools 🛠️

These are optional but improve reliability:

- Google Chrome or Chromium (used for PDF rendering and browser fallback fetch)
- `pdftotext` (verifies output PDFs and removes spam outputs)
- `wkhtmltopdf` (fallback renderer)
- `cloudscraper` (optional fetch helper)

## Mirror Pipeline Notes 🔁

The pipeline uses:

- `https://freedium-mirror.cfd` only

It validates content at multiple stages:

1. HTML validation to reject spam/landing pages
2. Title-based matching to confirm the requested article
3. PDF text validation to catch false positives

## Docs 📚

- Usage guide: `MEDIUM_USER_RANGE_SCRAPER_USAGE.md`
- Replication spec: `SCRAPER_V3_REPLICATION_SPEC.md`

## Output 📦

Generated PDFs are written to the output directory you pass in. Output artifacts are gitignored by default.
