# Scraper V3 Replication Spec

## Purpose

This document records the end-to-end behavior, debugging findings, and operating constraints for `scraper_v3.py` so the same scraper can be rebuilt or debugged quickly in the future.

Primary goal:

- Convert Agent Native Medium article URLs into full PDFs with text and images.

Hard constraints used in the final working design:

- Keep the third-party mirror-domain approach.
- Use only `https://freedium-mirror.cfd` as the mirror base.
- Reject fake article pages, generic landing pages, and betting/spam pages.
- Prefer validated HTML over rendering the live mirror URL directly.

## Current Contract

The scraper should:

1. Read Medium article URLs from `agent_native_article_urls.txt`.
2. Rewrite each Medium URL onto `https://freedium-mirror.cfd`.
3. Fetch mirror HTML with a layered strategy:
   - verified HTTP request
   - unverified HTTP request only after SSL verification failure
   - headless Chrome DOM fetch if HTTP fetch is blocked by an anti-bot page
4. Validate that the fetched HTML is the requested article.
5. Render the validated HTML to PDF.
6. Reject PDFs that still contain spam/betting content.
7. Delete bad output files instead of leaving false positives behind.

## Final End-to-End Flow

### Input

- Source file: `agent_native_article_urls.txt`
- Input format: one Medium URL per line

### URL Rewriting

For each Medium URL:

- Preserve the path
- Drop the query string
- Replace the host with `freedium-mirror.cfd`

Example:

- Input: `https://medium.com/@agentnativedev/codex-5-3-vs-opus-4-6-one-shot-examples-and-comparison-90b558e8eae8?source=...`
- Mirror URL: `https://freedium-mirror.cfd/@agentnativedev/codex-5-3-vs-opus-4-6-one-shot-examples-and-comparison-90b558e8eae8`

### Fetch Strategy

The fetch pipeline is intentionally layered.

1. Verified HTTP fetch
   - Uses `cloudscraper` when available
   - Falls back to `requests`

2. Unverified HTTP fetch
   - Used only when SSL verification fails
   - Uses plain `requests`, not `cloudscraper`
   - Suppresses `InsecureRequestWarning` only around that call

3. Headless Chrome DOM fetch
   - Used when HTTP fetch returns an anti-bot/interstitial page
   - Dumps the rendered DOM and re-enters the same validation pipeline

### HTML Validation

Fetched HTML is accepted only if all of the following are true:

- It is not a known betting/spam page.
- It is not the generic Freedium landing page.
- It appears to match the requested article title.

Validation is title-based, not strict raw-slug-based.

Reason:

- Mirror pages often do not contain the exact Medium slug including the hash suffix.
- Title matching is more stable than checking for the full article ID verbatim.

### Rendering Strategy

The scraper renders validated HTML, not the remote mirror URL.

Reason:

- Rendering the live mirror URL reintroduces trust in the mirror response at render time.
- Rendering the validated local HTML keeps fetch validation and render behavior aligned.

Primary renderer:

- Headless Chrome against a temporary local HTML file

Fallback renderer:

- `wkhtmltopdf` via `pdfkit`

### PDF Validation

After PDF generation:

- Run `pdftotext` when available
- Scan extracted text for betting/spam markers
- Delete the PDF if it is clearly wrong

## Root Causes Found During Debugging

### 1. SSL Fallback Broke With `cloudscraper`

Symptom:

- `Cannot set verify_mode to CERT_NONE when check_hostname is enabled`

Root cause:

- `cloudscraper` was being used for `verify=False` retries.

Fix:

- Keep `cloudscraper` only for verified requests.
- Use plain `requests` for unverified SSL fallback.

### 2. Fake Betting PDFs Were Treated As Success

Symptom:

- Generated PDFs contained India betting/casino content.

Root cause:

- Any `200 OK` mirror response was treated as a valid article page.

Fix:

- Added HTML validation before render.
- Added PDF content validation after render.

### 3. Rendering The Live Mirror URL Undid Validation

Symptom:

- Even after a clean fetch, the browser could still print unrelated mirror content.

Root cause:

- Chrome was rendering the remote mirror URL directly instead of the validated HTML.

Fix:

- Render a temporary local HTML file produced from validated HTML.

### 4. Validation Was Too Strict

Symptom:

- Valid article pages failed with:
  - `Fetched HTML does not reference expected article id`

Root cause:

- Validation required the exact Medium slug/hash string to appear in the HTML.

Fix:

- Replaced raw article-ID matching with token-overlap title matching.

### 5. Warning Suppression Introduced A New Crash

Symptom:

- `'NoneType' object does not support the context manager protocol`

Root cause:

- `urllib3.disable_warnings(...)` was incorrectly used as a context manager.

Fix:

- Replaced it with `warnings.catch_warnings()` and `warnings.simplefilter(...)`.

### 6. Anti-Bot Detection Produced False Positives

Symptom:

- Valid Freedium article pages were rejected as:
  - `Blocked by anti-bot protection`

Root cause:

- The detector flagged any occurrence of the word `cloudflare`.
- Valid article pages contained `cdnjs.cloudflare.com` assets and sometimes discussed Cloudflare in article text.

Fix:

- Tightened detection to real challenge markers only:
  - `Just a moment`
  - `Attention required`
  - `Cloudflare Ray ID`
  - `/cdn-cgi/challenge-platform/`
  - `cf-chl-`
  - `checking if the site connection is secure`
  - `please enable cookies`

### 7. HTTP Clients Can Still Hit Real Anti-Bot Pages

Symptom:

- Verified and unverified HTTP fetches can still hit interstitial pages.

Root cause:

- The mirror may treat programmatic clients differently from browsers.

Fix:

- Added a headless Chrome DOM-fetch fallback after HTTP anti-bot detection.

## Final Design Decisions

### Keep Only One Mirror Base

Chosen mirror base:

- `https://freedium-mirror.cfd`

Reason:

- The user explicitly wanted only this domain.
- Multi-domain fallback increased the chance of spam, redirects, and inconsistent content.

### Prefer HTML Validation Over Renderer Trust

Reason:

- Mirror domains are not authoritative.
- The renderer should not be allowed to pull fresh remote content after validation.

### Prefer Loose Title Matching Over Exact Slug Matching

Reason:

- Freedium article pages may rewrite, shorten, or omit the Medium slug hash.
- The human-readable title is the more stable identity signal.

## Operational Checklist

### Preconditions

- `scraper_v3.py` exists
- Google Chrome or Chromium is installed
- `agent_native_article_urls.txt` exists
- Optional but recommended:
  - `pdftotext`
  - `wkhtmltopdf`
  - `cloudscraper`

### Basic Verification

Run:

```bash
python3 -m py_compile scraper_v3.py
```

### Run The Scraper

```bash
python3 scraper_v3.py
```

Expected success path:

- Mirror URL printed
- possible SSL fallback log
- possible browser DOM fallback log
- validated PDF saved into `agent_native_articles/`

### If Output Looks Wrong

Check:

1. Is the fetched HTML a real article page or a challenge page?
2. Is HTML validation too weak?
3. Is title matching too strict for that page?
4. Did PDF generation reintroduce remote content?
5. Does `pdftotext` confirm the PDF is valid article text?

## Known Failure Modes

### Mirror DNS Or Reachability Failure

Observed shape:

- host resolution failures
- connection errors

Interpretation:

- network or mirror outage, not scraper logic

### Chrome DOM Fetch Instability

Observed in this environment:

- headless Chrome could abort on some local `--dump-dom` tests inside the sandbox

Interpretation:

- environment-specific Chrome behavior can differ from the user’s normal machine

Mitigation:

- keep the browser fallback path isolated
- treat browser-fallback failures as diagnostics, not proof that the mirror is invalid

### Mirror Returns Valid HTML But Wrong Article

Mitigation:

- title matching
- spam marker detection
- PDF post-validation

## Replication Guide

If this scraper needs to be rebuilt from scratch, preserve this order:

1. Implement Medium URL to mirror URL rewriting.
2. Implement layered fetch:
   - verified HTTP
   - unverified HTTP on SSL failure only
   - browser DOM fetch on anti-bot detection
3. Implement HTML validation:
   - spam detection
   - landing-page detection
   - title similarity matching
4. Render validated local HTML, not live remote URLs.
5. Validate final PDF text and delete bad files.
6. Add logs that identify which stage failed:
   - SSL
   - anti-bot
   - HTML validation
   - browser fallback
   - PDF validation

## Suggested Improvements

### 1. Save Failure Artifacts

Add an optional debug mode that stores:

- raw fetched HTML
- Chrome DOM HTML
- extracted PDF text

This would make future debugging much faster.

### 2. Add Structured Logs

Current logs are readable but not machine-friendly.

Improve with:

- article URL
- mirror URL
- fetch method used
- renderer used
- validation result
- final output path

JSON logs would make batch debugging easier.

### 3. Add Unit Tests For Validation Logic

Recommended tests:

- spam page rejected
- Freedium landing page rejected
- valid Freedium article accepted
- Cloudflare challenge page rejected
- article title overlap accepted without raw slug match

### 4. Add A Debug Snapshot Directory

Recommended folder:

- `debug_snapshots/`

Store per-article artifacts with stable filenames to compare mirror responses over time.

### 5. Add Retry Budget And Backoff

Current fetch strategy is functional but not policy-driven.

Improve with:

- explicit retry counts
- exponential backoff
- timeout tuning by stage

### 6. Add A Browser Session Strategy

If browser fallback becomes important, consider:

- `--user-data-dir` for a stable headless profile
- Playwright instead of raw Chrome CLI
- optional cookie persistence

This would make anti-bot handling more reliable.

### 7. Add A Strict “Verified Only” Mode

Sometimes quality matters more than throughput.

Useful optional mode:

- skip article if browser fallback was required
- save only pages that passed direct HTTP fetch + validation

### 8. Add A Batch Cleanup Tool

A small helper script should scan all generated PDFs and remove ones matching spam markers.

This was done manually during debugging and should be codified.

## Recommended Next Files

If this workflow becomes permanent, consider adding:

- `SCRAPER_V3_REPLICATION_SPEC.md`
- `scraper_v3_cleanup.py`
- `tests/test_scraper_v3_validation.py`
- `debug_snapshots/`

## Summary

The core lesson is simple:

- the mirror is useful, but not trustworthy by default
- fetch success is not article success
- render success is not content success

The stable version of this scraper works because it validates at every boundary:

- fetched HTML
- rendered PDF
- final saved output
