#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class PostRecord:
    post_id: str
    title: str
    published_at_ms: int
    url: str


def _stderr(message: str) -> None:
    print(message, flush=True, file=__import__("sys").stderr)


def _strip_medium_prefix(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in response")
    return text[start:]


def _build_proxy_url(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return f"https://r.jina.ai/{url}"
    query = urlencode(params, doseq=True)
    separator = "&" if "?" in url else "?"
    return f"https://r.jina.ai/{url}{separator}{query}"


def _get_json(url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
    }

    last_error: Exception | None = None
    for target_url in (url, _build_proxy_url(url, params)):
        try:
            if target_url == url:
                response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
            else:
                response = requests.get(target_url, headers=headers, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return json.loads(_strip_medium_prefix(response.text))
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Failed to fetch JSON from {url}") from last_error


def _parse_date_to_range_bounds(date_str: str, *, is_end: bool) -> int:
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    day_time = time.max if is_end else time.min
    dt = datetime.combine(day, day_time, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _normalize_username(username: str) -> str:
    normalized = username.strip()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("Username must not be empty")
    return normalized


def _resolve_user(username: str) -> tuple[str, str]:
    profile_url = f"https://medium.com/@{username}?format=json"
    data = _get_json(profile_url)
    payload = data.get("payload") or {}
    user = payload.get("user") or {}
    user_id = user.get("userId")
    canonical_username = user.get("username")
    if not user_id or not canonical_username:
        raise RuntimeError(f"Could not resolve Medium user for @{username}")
    return str(user_id), str(canonical_username)


def _coerce_publish_ms(post: dict[str, Any]) -> int | None:
    for key in ("firstPublishedAt", "publishedAt"):
        value = post.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _build_post_url(username: str, unique_slug: str) -> str:
    return f"https://medium.com/@{username}/{unique_slug}"


def _extract_posts_from_payload(
    payload: dict[str, Any],
    *,
    username: str,
    include_responses: bool,
) -> list[PostRecord]:
    references = payload.get("references") or {}
    posts = references.get("Post") or {}
    if not isinstance(posts, dict):
        return []

    out: list[PostRecord] = []
    for post_id, post in posts.items():
        if not isinstance(post, dict):
            continue
        unique_slug = post.get("uniqueSlug")
        if not unique_slug:
            continue
        if not include_responses and post.get("inResponseToPostId"):
            continue
        published_at_ms = _coerce_publish_ms(post)
        if published_at_ms is None:
            continue
        title = str(post.get("title") or "").strip()
        out.append(
            PostRecord(
                post_id=str(post_id),
                title=title,
                published_at_ms=published_at_ms,
                url=_build_post_url(username, str(unique_slug)),
            )
        )
    return out


def _get_next_params(data: dict[str, Any]) -> dict[str, Any] | None:
    for container in (data, data.get("payload") or {}):
        paging = container.get("paging")
        if isinstance(paging, dict) and isinstance(paging.get("next"), dict):
            return dict(paging["next"])
    return None


def _fetch_all_posts(user_id: str, *, username: str, include_responses: bool) -> list[PostRecord]:
    base_url = f"https://medium.com/_/api/users/{user_id}/profile/stream"
    params: dict[str, Any] | None = None
    seen_post_ids: set[str] = set()
    results: list[PostRecord] = []

    while True:
        data = _get_json(base_url, params=params)
        payload = data.get("payload") or {}
        for post in _extract_posts_from_payload(payload, username=username, include_responses=include_responses):
            if post.post_id in seen_post_ids:
                continue
            seen_post_ids.add(post.post_id)
            results.append(post)

        params = _get_next_params(data)
        if not params:
            break

    results.sort(key=lambda item: item.published_at_ms, reverse=True)
    return results


def _filter_posts(posts: list[PostRecord], *, start_ms: int, end_ms: int) -> list[PostRecord]:
    return [post for post in posts if start_ms <= post.published_at_ms <= end_ms]


def _record_to_json(post: PostRecord) -> dict[str, Any]:
    published_at = datetime.fromtimestamp(post.published_at_ms / 1000, tz=timezone.utc)
    return {
        "post_id": post.post_id,
        "title": post.title,
        "published_at": published_at.isoformat(),
        "url": post.url,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List Medium article links for a username within a date range.")
    parser.add_argument("--username", required=True, help="Medium username, with or without leading @.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date in YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date in YYYY-MM-DD.")
    parser.add_argument("--out", type=Path, help="Optional output file path.")
    parser.add_argument("--include-responses", action="store_true", help="Include Medium responses.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of plain URLs.")
    args = parser.parse_args()

    username = _normalize_username(args.username)
    start_ms = _parse_date_to_range_bounds(args.start_date, is_end=False)
    end_ms = _parse_date_to_range_bounds(args.end_date, is_end=True)
    if start_ms > end_ms:
        raise SystemExit("start-date must be less than or equal to end-date")

    user_id, canonical_username = _resolve_user(username)
    _stderr(f"Resolved @{canonical_username} to user id {user_id}")

    posts = _fetch_all_posts(
        user_id,
        username=canonical_username,
        include_responses=args.include_responses,
    )
    _stderr(f"Fetched {len(posts)} published posts before date filtering")

    filtered = _filter_posts(posts, start_ms=start_ms, end_ms=end_ms)
    _stderr(f"Matched {len(filtered)} posts in requested date range")

    if args.json:
        output = json.dumps([_record_to_json(post) for post in filtered], indent=2)
    else:
        output = "\n".join(post.url for post in filtered)

    if output:
        output += "\n"

    if args.out:
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
