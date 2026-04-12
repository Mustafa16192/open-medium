from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse, urlunparse

import requests

from medium_links_by_date import _fetch_all_posts, _filter_posts, _resolve_user
from scraper_v3 import HEADERS, _fetch_html_with_chrome, _is_anti_bot_html, download_and_convert_to_pdf


ARCHIVE_BASE = "https://medium.com"
PROFILE_PROXY_BASE = "https://r.jina.ai/http://medium.com"


@dataclass(frozen=True)
class ArticleRecord:
    url: str
    published_date: dt.date


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Medium article URLs for a user in a date range, then fetch them "
            "through the Freedium mirror pipeline into an output directory."
        )
    )
    parser.add_argument("--username", required=True, help="Medium username, handle, or display name")
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD")
    parser.add_argument(
        "--output-dir",
        help="Directory for generated PDFs. Defaults to <username>_<start>_<end>_articles",
    )
    parser.add_argument(
        "--save-url-list",
        action="store_true",
        help="Write the discovered in-range article URLs into urls.txt inside the output directory.",
    )
    return parser.parse_args()


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date: {value}. Use YYYY-MM-DD.") from exc


def _iter_months(start_date: dt.date, end_date: dt.date) -> Iterable[tuple[int, int]]:
    year = start_date.year
    month = start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _archive_url(username: str, year: int, month: int) -> str:
    return f"{ARCHIVE_BASE}/@{username}/archive/{year}/{month:02d}"


def _normalize_medium_url(url: str) -> str:
    parsed = urlparse(html_lib.unescape(url))
    path = parsed.path
    if not path:
        return ""
    return urlunparse(("https", "medium.com", path, "", "", ""))


def _profile_proxy_url(username: str) -> str:
    return f"{PROFILE_PROXY_BASE}/@{username}"


def _fetch_html(url: str) -> str:
    last_error: Exception | None = None

    for verify in (True, False):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=(10, 30),
                verify=verify,
            )
            response.raise_for_status()
            if _is_anti_bot_html(response.text):
                raise RuntimeError("Blocked by anti-bot protection")
            return response.text
        except requests.exceptions.SSLError as exc:
            last_error = exc
            if verify:
                print(f"  SSL verify failed for {url}, retrying with unverified SSL context")
                continue
            break
        except Exception as exc:
            last_error = exc
            break

    try:
        print(f"  HTTP fetch blocked for {url}, retrying with headless Chrome DOM fetch")
        html = _fetch_html_with_chrome(url)
        if _is_anti_bot_html(html):
            raise RuntimeError("Blocked by anti-bot protection")
        return html
    except Exception as exc:
        last_error = exc

    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def _extract_archive_urls(username: str, html: str) -> list[str]:
    absolute_pattern = re.compile(
        rf"https?://medium\.com/@{re.escape(username)}/[^/?#\"'\s)]+-[0-9a-f]{{12}}(?:\?[^\"'<\\s)]*)?",
        re.IGNORECASE,
    )
    relative_pattern = re.compile(
        rf"/@{re.escape(username)}/[^/?#\"'\s)]+-[0-9a-f]{{12}}(?:\?[^\"'<\\s)]*)?",
        re.IGNORECASE,
    )

    urls: set[str] = set()
    for match in absolute_pattern.findall(html):
        normalized = _normalize_medium_url(match)
        if normalized:
            urls.add(normalized)

    for match in relative_pattern.findall(html):
        normalized = _normalize_medium_url(f"{ARCHIVE_BASE}{match}")
        if normalized:
            urls.add(normalized)

    return sorted(urls)


def _fetch_profile_page_text(username: str) -> str:
    response = requests.get(
        _profile_proxy_url(username),
        headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "text/plain,text/html,application/xhtml+xml,*/*",
        },
        timeout=(10, 30),
    )
    response.raise_for_status()
    return response.text


def _parse_profile_date_line(value: str, *, default_year: int) -> dt.date | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    for format_string in ("%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = dt.datetime.strptime(cleaned, format_string)
        except ValueError:
            continue
        return dt.date(parsed.year, parsed.month, parsed.day)

    for format_string in ("%b %d", "%B %d"):
        try:
            parsed = dt.datetime.strptime(f"{default_year} {cleaned}", f"%Y {format_string}")
        except ValueError:
            continue
        return dt.date(parsed.year, parsed.month, parsed.day)

    return None


def _extract_profile_article_records(username: str, profile_text: str, start_date: dt.date, end_date: dt.date) -> list[ArticleRecord]:
    lines = profile_text.splitlines()
    url_pattern = re.compile(
        rf"https?://medium\.com/@{re.escape(username)}/[^)\s]+",
        re.IGNORECASE,
    )

    records: list[ArticleRecord] = []
    seen_urls: set[str] = set()

    for index, line in enumerate(lines):
        url_match = url_pattern.search(line)
        if not url_match:
            continue

        url = _normalize_medium_url(url_match.group(0))
        if not url or url in seen_urls:
            continue

        published_date: dt.date | None = None
        for offset in range(1, 8):
            lookahead_index = index + offset
            if lookahead_index >= len(lines):
                break
            published_date = _parse_profile_date_line(lines[lookahead_index], default_year=end_date.year)
            if published_date:
                break

        if published_date and start_date <= published_date <= end_date:
            seen_urls.add(url)
            records.append(ArticleRecord(url=url, published_date=published_date))

    records.sort(key=lambda record: (record.published_date, record.url))
    return records


def _extract_published_date(html: str) -> dt.date:
    patterns = (
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"datePublished"\s*content\s*=\s*"([^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            return dt.date.fromisoformat(match.group(1)[:10])
    raise RuntimeError("Could not extract published date from article HTML")


def _discover_article_records(username: str, start_date: dt.date, end_date: dt.date) -> list[ArticleRecord]:
    try:
        user_id, canonical_username = _resolve_user(username)
        print(f"-> Discovering posts via Medium API for @{canonical_username} (user id {user_id})")

        start_ms = int(dt.datetime.combine(start_date, dt.time.min, tzinfo=dt.timezone.utc).timestamp() * 1000)
        end_ms = int(dt.datetime.combine(end_date, dt.time.max, tzinfo=dt.timezone.utc).timestamp() * 1000)

        posts = _fetch_all_posts(
            user_id,
            username=canonical_username,
            include_responses=False,
        )
        filtered_posts = _filter_posts(posts, start_ms=start_ms, end_ms=end_ms)

        records = [
            ArticleRecord(
                url=post.url,
                published_date=dt.datetime.fromtimestamp(post.published_at_ms / 1000, tz=dt.timezone.utc).date(),
            )
            for post in filtered_posts
        ]
        records.sort(key=lambda record: (record.published_date, record.url))
        print(f"  Matched {len(records)} article(s) in requested date range via API")
        if records:
            return records
        print("  API discovery returned 0 articles in the requested range; trying archive/profile fallbacks")
    except Exception as api_error:
        print(f"  API discovery failed for @{username}: {api_error}")
        print("  Falling back to archive scraping")

    candidate_urls: set[str] = set()

    for year, month in _iter_months(start_date, end_date):
        archive = _archive_url(username, year, month)
        print(f"-> Discovering archive page: {archive}")
        try:
            html = _fetch_html(archive)
            found = _extract_archive_urls(username, html)
            print(f"  Found {len(found)} candidate article URLs in {year}-{month:02d}")
            candidate_urls.update(found)
        except Exception as exc:
            print(f"  Skipping archive page {archive}: {exc}")

    if not candidate_urls:
        print("  Archive discovery found no candidate URLs; trying profile-page fallback")
        try:
            profile_text = _fetch_profile_page_text(username)
            profile_records = _extract_profile_article_records(username, profile_text, start_date, end_date)
            if profile_records:
                print(f"  Found {len(profile_records)} article(s) in profile fallback")
                return profile_records

            found = _extract_archive_urls(username, profile_text)
            print(f"  Found {len(found)} candidate article URLs in profile fallback")
            candidate_urls.update(found)
        except Exception as exc:
            print(f"  Profile page fallback failed for @{username}: {exc}")

    records: list[ArticleRecord] = []
    for url in sorted(candidate_urls):
        print(f"-> Inspecting article metadata: {url}")
        try:
            html = _fetch_html(url)
            published_date = _extract_published_date(html)
            if start_date <= published_date <= end_date:
                records.append(ArticleRecord(url=url, published_date=published_date))
        except Exception as exc:
            print(f"  Skipping article metadata fetch for {url}: {exc}")

    records.sort(key=lambda record: (record.published_date, record.url))
    return records


def _default_output_dir(username: str, start_date: dt.date, end_date: dt.date) -> str:
    return f"{username}_{start_date.isoformat()}_{end_date.isoformat()}_articles"


def _write_url_list(output_dir: str, records: list[ArticleRecord]) -> None:
    path = f"{output_dir}/urls.txt"
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(f"{record.published_date.isoformat()} {record.url}\n")


def main() -> int:
    args = _parse_args()
    username = args.username.lstrip("@").strip()
    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)

    if start_date > end_date:
        print("Error: --start-date must be on or before --end-date.")
        return 1

    output_dir = args.output_dir or _default_output_dir(username, start_date, end_date)

    print(f"Account: {username}")
    print(f"Date range: {start_date.isoformat()} to {end_date.isoformat()}")
    print(f"Output dir: ./{output_dir}\n")

    records = _discover_article_records(username, start_date, end_date)
    print(f"\nDiscovered {len(records)} article(s) in range.\n")

    if args.save_url_list:
        import os

        os.makedirs(output_dir, exist_ok=True)
        _write_url_list(output_dir, records)
        print(f"Saved discovered URL list to ./{output_dir}/urls.txt\n")

    success_count = 0
    for record in records:
        print(f"Downloading {record.published_date.isoformat()}: {record.url}")
        if download_and_convert_to_pdf(record.url, output_dir=output_dir):
            success_count += 1

    print(
        f"\nDone. Successfully saved {success_count}/{len(records)} articles "
        f"to ./{output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
