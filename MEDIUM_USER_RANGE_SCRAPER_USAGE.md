# Medium User Range Scraper Usage Guide

## Overview

`medium_user_range_scraper.py` is the end-to-end entrypoint for:

1. taking a Medium username
2. discovering that user’s article URLs from Medium archive pages
3. filtering articles by an inclusive date range
4. downloading those articles through the Freedium mirror implementation
5. saving the final PDFs into an output directory

This script reuses the validated mirror pipeline from `scraper_v3.py`.

## What The Script Does

Given:

- a Medium username
- a start date
- an end date

the script will:

1. request each monthly archive page that intersects the date range
2. extract candidate article URLs for that user
3. fetch each article page and read its published date
4. keep only articles whose published date falls within the range
5. run each retained URL through the existing mirror-based PDF downloader

## Files

Primary script:

- [medium_user_range_scraper.py](/Users/mustafa/Library/Mobile%20Documents/com~apple~CloudDocs/Work/Masters/umich/2%20semester/medium_articles/medium_user_range_scraper.py)

Mirror pipeline dependency:

- [scraper_v3.py](/Users/mustafa/Library/Mobile%20Documents/com~apple~CloudDocs/Work/Masters/umich/2%20semester/medium_articles/scraper_v3.py)

## Requirements

### Required Python Dependency

Current `requirements.txt` includes:

- `requests>=2.31.0`

Install:

```bash
pip install -r requirements.txt
```

### Recommended Local Tools

These are not all strictly required, but they materially improve reliability:

- Google Chrome or Chromium
- `pdftotext`
- `wkhtmltopdf`
- `cloudscraper`

Why they matter:

- Chrome/Chromium is used for PDF rendering and browser fallback fetches.
- `pdftotext` is used to validate generated PDFs and detect bad content.
- `wkhtmltopdf` is used as a fallback renderer.
- `cloudscraper` can help with some mirror fetches.

## Command Syntax

```bash
python3 medium_user_range_scraper.py \
  --username USERNAME \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  [--output-dir OUTPUT_DIR] \
  [--save-url-list]
```

## Arguments

### `--username`

Medium username.

Examples:

- `agentnativedev`
- `@agentnativedev`

Notes:

- The script strips a leading `@` automatically.
- Pass only the username, not the full profile URL.

### `--start-date`

Inclusive lower bound in `YYYY-MM-DD` format.

### `--end-date`

Inclusive upper bound in `YYYY-MM-DD` format.

Important:

- The date range is inclusive on both ends.
- `--start-date` must be on or before `--end-date`.

### `--output-dir`

Optional output directory for the generated PDFs.

If omitted, the script uses:

```text
<username>_<start-date>_<end-date>_articles
```

Example:

```text
agentnativedev_2026-02-01_2026-03-09_articles
```

### `--save-url-list`

Optional flag.

If provided, the script creates:

- `urls.txt` inside the output directory

Each line contains:

- published date
- canonical Medium article URL

## Common Usage Examples

### Basic Run

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-02-01 \
  --end-date 2026-03-09
```

### Save Into A Custom Directory

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-01-01 \
  --end-date 2026-01-31 \
  --output-dir january_articles
```

### Save The Discovered URL List Too

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-02-01 \
  --end-date 2026-03-09 \
  --output-dir agent_native_articles_range \
  --save-url-list
```

### Single-Day Range

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-03-09 \
  --end-date 2026-03-09
```

## Expected Console Output

Typical flow:

1. Script prints the username, range, and output directory.
2. Script visits each relevant monthly archive page.
3. Script prints how many candidate URLs were found per month.
4. Script inspects each article page to extract `published_date`.
5. Script prints how many in-range articles were discovered.
6. Script downloads each article through the mirror pipeline.
7. Script prints final success count.

Example shape:

```text
Username: @agentnativedev
Date range: 2026-02-01 to 2026-03-09
Output dir: ./agent_native_articles_range

-> Discovering archive page: https://medium.com/@agentnativedev/archive/2026/02
  Found 18 candidate article URLs in 2026-02
-> Discovering archive page: https://medium.com/@agentnativedev/archive/2026/03
  Found 12 candidate article URLs in 2026-03

Discovered 21 article(s) in range.

Downloading 2026-02-05: https://medium.com/@agentnativedev/...
...

Done. Successfully saved 21/21 articles to ./agent_native_articles_range
```

## Output Structure

### PDFs

Generated PDFs are written into the chosen output directory.

Filename format:

- derived from the Medium article slug
- sanitized for filesystem safety

Example:

```text
agent_native_articles_range/
  codex-5-3-vs-opus-4-6-one-shot-examples-and-comparison-90b558e8eae8.pdf
  why-codex-became-my-default-over-claude-code-for-now-8f938812ef09.pdf
```

### Optional URL List

If `--save-url-list` is provided:

```text
agent_native_articles_range/
  urls.txt
```

Example line format:

```text
2026-02-05 https://medium.com/@agentnativedev/codex-5-3-vs-opus-4-6-one-shot-examples-and-comparison-90b558e8eae8
```

## Discovery Logic

The script discovers articles by scanning Medium archive pages:

```text
https://medium.com/@<username>/archive/YYYY/MM
```

For each monthly archive page in the requested range:

- candidate article links are extracted for that username only
- duplicates are removed
- each candidate article page is fetched
- publication date is extracted from page metadata
- only in-range articles are retained

This means the range filtering is based on actual article publish dates, not only archive page month membership.

## Mirror Download Logic

Once the article URL list is built, each article is passed into `scraper_v3.py`.

That mirror pipeline currently:

- rewrites Medium URLs onto `https://freedium-mirror.cfd`
- fetches mirror HTML through layered HTTP/browser fallback logic
- validates that the HTML matches the requested article
- renders validated HTML to PDF
- rejects spam or unrelated outputs

## Important Behavior Notes

### Query Parameters Are Ignored

If Medium URLs contain `?source=...`, those query parameters do not matter for discovery or PDF generation.

### Username Matching Is Strict

Archive URL extraction only keeps links matching the exact username passed in.

### Dates Are Inclusive

An article published exactly on the `start-date` or `end-date` is included.

### Archive Discovery Is Month-Based First

If your range spans multiple months, the script will fetch one Medium archive page per month in that span.

## How To Check The CLI Interface

```bash
python3 medium_user_range_scraper.py --help
```

## Troubleshooting

### Error: `--start-date must be on or before --end-date`

Cause:

- the range is reversed

Fix:

- swap the dates

### Error: `Invalid date: ... Use YYYY-MM-DD`

Cause:

- a date argument is malformed

Fix:

- use ISO format exactly, for example `2026-03-09`

### Error: `Blocked by anti-bot protection`

Cause:

- Medium archive page fetch or mirror fetch hit an interstitial/challenge page

What to check:

- Chrome is installed and accessible
- network access to Medium and `freedium-mirror.cfd` works
- the profile/month archive pages are reachable in a browser

### No Articles Found

Possible causes:

- wrong username
- no posts in that date range
- archive page format changed
- Medium returned incomplete archive HTML

What to check:

- open `https://medium.com/@<username>/archive/YYYY/MM` manually
- verify the account publishes under that username
- try a broader date range

### PDFs Not Generated But URLs Were Found

Possible causes:

- mirror fetch failure
- validation rejected mirror HTML
- Chrome/wkhtmltopdf missing

What to check:

- confirm Chrome is installed
- confirm mirror access works in a browser
- inspect console logs for validation failures

### Browser Fallback Problems

If the script logs a browser DOM fetch attempt and still fails:

- the target page may still be blocked
- the local browser environment may differ from the expected CLI environment

## Recommended Environment Setup

### Minimum

```bash
pip install -r requirements.txt
```

### Better

Install:

- Google Chrome
- `pdftotext`
- `wkhtmltopdf`
- `cloudscraper`

Example for Python package:

```bash
pip install cloudscraper
```

## Suggested Workflow

### For A New Username

1. Start with a narrow date range.
2. Add `--save-url-list`.
3. Confirm the discovered URLs look correct.
4. Expand the date range if needed.

### For Large Ranges

If scraping many months:

1. run a few months first
2. verify output quality
3. then run the larger full range

This reduces the chance of generating a large batch of bad output if Medium or the mirror behavior changes.

## Example End-to-End Session

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-02-01 \
  --end-date 2026-03-09 \
  --output-dir agent_native_articles_range \
  --save-url-list
```

Expected artifacts:

```text
agent_native_articles_range/
  urls.txt
  7-local-llm-families-to-replace-claude-codex-for-everyday-tasks-25ba74c3635d.pdf
  codex-5-3-vs-opus-4-6-one-shot-examples-and-comparison-90b558e8eae8.pdf
  ...
```

## Current Limitations

- The script depends on Medium archive pages being discoverable and parseable.
- The script depends on the current Freedium mirror path format.
- Date extraction depends on metadata patterns like `article:published_time` or `datePublished`.
- The browser fallback path depends on local Chrome behavior.

## Related Docs

For the deeper scraper design and debugging history, see:

- [SCRAPER_V3_REPLICATION_SPEC.md](/Users/mustafa/Library/Mobile%20Documents/com~apple~CloudDocs/Work/Masters/umich/2%20semester/medium_articles/SCRAPER_V3_REPLICATION_SPEC.md)
