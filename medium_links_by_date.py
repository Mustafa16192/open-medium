#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse, urlunparse

import requests


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 60
SEARCH_RESULTS_TIMEOUT_SECONDS = 30
RSS_TIMEOUT_SECONDS = 30


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


def _get_text(url: str, *, params: dict[str, Any] | None = None) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    last_error: Exception | None = None
    for target_url in (url, _build_proxy_url(url, params)):
        try:
            if target_url == url:
                response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
            else:
                response = requests.get(target_url, headers=headers, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Failed to fetch text from {url}") from last_error


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


def _looks_like_handle(username: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", username))


def _looks_like_user_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Fa-f0-9]{12,}", value))


def _parse_possible_medium_url(value: str):
    raw = value.strip()
    if not raw:
        return None
    if "medium.com" not in raw.lower() and not raw.lower().startswith("http"):
        return None
    candidate = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    try:
        return urlparse(candidate)
    except ValueError:
        return None


def _extract_medium_handle_from_url(value: str) -> str | None:
    parsed = _parse_possible_medium_url(value)
    if parsed is None or not parsed.hostname:
        return None

    host = parsed.hostname.lower().replace("www.", "")
    if host == "medium.com":
        segments = [segment for segment in parsed.path.split("/") if segment]
        if segments and segments[0].startswith("@"):
            handle = segments[0][1:].strip()
            if handle and _looks_like_handle(handle):
                return handle

    if host.endswith(".medium.com"):
        subdomain = host[: -len(".medium.com")].strip()
        if subdomain and _looks_like_handle(subdomain):
            return subdomain

    return None


def _extract_medium_user_id(value: str) -> str | None:
    normalized = value.strip()
    if _looks_like_user_id(normalized):
        return normalized.lower()

    parsed = _parse_possible_medium_url(value)
    if parsed is None or not parsed.hostname:
        return None

    host = parsed.hostname.lower().replace("www.", "")
    if host != "medium.com":
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    if (
        len(segments) >= 4
        and segments[0] == "me"
        and segments[1] == "following-feed"
        and segments[2] == "writers"
        and _looks_like_user_id(segments[3])
    ):
        return segments[3].lower()

    return None


def _resolve_user_from_profile(username: str) -> tuple[str, str]:
    profile_urls = [
        f"https://medium.com/@{username}?format=json",
        f"https://{username}.medium.com/?format=json",
    ]

    last_error: Exception | None = None
    for profile_url in profile_urls:
        try:
            data = _get_json(profile_url)
            payload = data.get("payload") or {}
            user = payload.get("user") or {}
            user_id = user.get("userId")
            canonical_username = user.get("username")
            if not user_id or not canonical_username:
                raise RuntimeError(f"Could not resolve Medium user for @{username}")
            return str(user_id), str(canonical_username)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not resolve Medium user for @{username}: {last_error}") from last_error


def _fetch_profile_page_text(username: str) -> str:
    profile_url = f"http://medium.com/@{username}"
    proxy_url = _build_proxy_url(profile_url)
    response = requests.get(
        proxy_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/plain,text/html,application/xhtml+xml,*/*",
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


def _extract_profile_identity(profile_text: str) -> tuple[str | None, str | None]:
    user_id_match = re.search(r"user_profile_page[-]+([a-f0-9]+)[-]+", profile_text, re.IGNORECASE)
    username_match = re.search(r"URL Source:\s*https?://medium\.com/@([^\s/?#]+)", profile_text, re.IGNORECASE)
    user_id = user_id_match.group(1) if user_id_match else None
    canonical_username = username_match.group(1) if username_match else None
    return user_id, canonical_username


def _resolve_user_from_profile_page(username: str) -> tuple[str, str]:
    profile_text = _fetch_profile_page_text(username)
    user_id, canonical_username = _extract_profile_identity(profile_text)
    if not user_id:
        raise RuntimeError(f"Could not resolve Medium user for @{username} from profile page text")
    return user_id, canonical_username or username


def _resolve_exact_profile(username: str) -> tuple[str, str]:
    last_error: Exception | None = None
    for resolver in (_resolve_user_from_profile, _resolve_user_from_profile_page):
        try:
            return resolver(username)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not resolve Medium user for @{username}: {last_error}") from last_error


def _extract_identity_from_profile_stream_payload(
    data: dict[str, Any],
    *,
    requested_user_id: str,
) -> tuple[str, str] | None:
    payload = data.get("payload") or {}
    references = payload.get("references") or {}
    users = references.get("User") if isinstance(references, dict) else None

    candidate_users: list[dict[str, Any]] = []
    if isinstance(users, dict):
        exact_match = users.get(requested_user_id)
        if isinstance(exact_match, dict):
            candidate_users.append(exact_match)
        for candidate in users.values():
            if isinstance(candidate, dict) and candidate not in candidate_users:
                candidate_users.append(candidate)

    direct_user = payload.get("user")
    if isinstance(direct_user, dict) and direct_user not in candidate_users:
        candidate_users.append(direct_user)

    fallback_username: str | None = None
    for candidate in candidate_users:
        candidate_user_id = str(candidate.get("userId") or candidate.get("id") or "").strip().lower()
        canonical_username = str(candidate.get("username") or "").strip()
        if not canonical_username:
            continue
        if candidate_user_id == requested_user_id:
            return requested_user_id, canonical_username
        if fallback_username is None:
            fallback_username = canonical_username

    if fallback_username:
        return requested_user_id, fallback_username
    return None


def _extract_identity_from_profile_stream_text(
    response_text: str,
    *,
    requested_user_id: str,
) -> tuple[str, str] | None:
    escaped_user_id = re.escape(requested_user_id)
    patterns = (
        rf'"userId":"{escaped_user_id}".{{0,2000}}?"username":"([^"]+)"',
        rf'"username":"([^"]+)".{{0,2000}}?"userId":"{escaped_user_id}"',
    )
    for pattern in patterns:
        match = re.search(pattern, response_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            canonical_username = match.group(1).strip()
            if canonical_username:
                return requested_user_id, canonical_username
    return None


def _resolve_user_from_user_id(user_id: str) -> tuple[str, str]:
    normalized_user_id = user_id.strip().lower()
    if not _looks_like_user_id(normalized_user_id):
        raise RuntimeError(f"Invalid Medium user id: {user_id}")

    base_url = f"https://medium.com/_/api/users/{normalized_user_id}/profile/stream"
    last_error: Exception | None = None

    try:
        data = _get_json(base_url)
        identity = _extract_identity_from_profile_stream_payload(
            data,
            requested_user_id=normalized_user_id,
        )
        if identity:
            return identity
    except Exception as exc:
        last_error = exc

    try:
        response_text = _get_text(base_url)
        identity = _extract_identity_from_profile_stream_text(
            response_text,
            requested_user_id=normalized_user_id,
        )
        if identity:
            return identity
    except Exception as exc:
        last_error = exc

    raise RuntimeError(f"Could not resolve Medium user for id {user_id}: {last_error}") from last_error


def _search_profile_urls(query: str) -> list[str]:
    search_url = f"https://medium.com/search?q={quote(query)}"
    html = _get_text(search_url)
    candidates: list[str] = []

    for match in re.finditer(r'https://medium\.com/@([^/?#"\s)]+)', html, re.IGNORECASE):
        candidates.append(match.group(1))

    blocked_subdomains = {
        "cdn",
        "cdn-images",
        "cdn-images-1",
        "cdn-images-2",
        "img",
        "image",
        "images",
        "media",
        "miro",
        "static",
        "stat",
    }

    for match in re.finditer(r'https://([a-z0-9-]+)\.medium\.com/?', html, re.IGNORECASE):
        candidate = match.group(1).strip()
        if candidate.lower() in blocked_subdomains:
            continue
        candidates.append(match.group(1))

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return unique_candidates


def _resolve_user(username: str) -> tuple[str, str]:
    normalized = _normalize_username(username)
    last_error: Exception | None = None

    medium_handle = _extract_medium_handle_from_url(normalized)
    if medium_handle:
        normalized = medium_handle

    medium_user_id = _extract_medium_user_id(normalized)
    if medium_user_id:
        return _resolve_user_from_user_id(medium_user_id)

    if _looks_like_handle(normalized):
        try:
            return _resolve_exact_profile(normalized)
        except Exception as exc:
            last_error = exc

    if " " in normalized:
        try:
            for candidate in _search_profile_urls(normalized):
                try:
                    return _resolve_exact_profile(candidate)
                except Exception as exc:
                    last_error = exc
                    continue
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not resolve Medium user for {username!r}: {last_error}") from last_error


def _coerce_publish_ms(post: dict[str, Any]) -> int | None:
    for key in ("firstPublishedAt", "publishedAt"):
        value = post.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _build_post_url(username: str, unique_slug: str) -> str:
    return f"https://medium.com/@{username}/{unique_slug}"


def _normalize_post_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    if not path:
        return ""
    return urlunparse(("https", "medium.com", path, "", "", ""))


def _parse_rss_publish_ms(item: ET.Element) -> int | None:
    pub_date = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated")
    if not pub_date:
        return None
    try:
        return int(parsedate_to_datetime(pub_date).astimezone(timezone.utc).timestamp() * 1000)
    except Exception:
        return None


def _extract_posts_from_rss(xml_text: str) -> list[PostRecord]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items = root.findall("./channel/item")
    if not items:
        items = root.findall(".//item")

    out: list[PostRecord] = []
    for item in items:
        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        published_at_ms = _parse_rss_publish_ms(item)
        if not link or published_at_ms is None:
            continue

        normalized_link = _normalize_post_url(link)
        if not normalized_link:
            continue

        title = (item.findtext("title") or "").strip()
        slug = normalized_link.rstrip("/").rsplit("/", 1)[-1]
        out.append(
            PostRecord(
                post_id=slug,
                title=title,
                published_at_ms=published_at_ms,
                url=normalized_link,
            )
        )

    return out


def _fetch_posts_from_rss(username: str) -> list[PostRecord]:
    feed_urls = [
        f"https://medium.com/feed/@{username}",
        f"https://{username}.medium.com/feed",
    ]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }

    last_error: Exception | None = None
    for feed_url in feed_urls:
        try:
            response = requests.get(feed_url, headers=headers, timeout=RSS_TIMEOUT_SECONDS)
            response.raise_for_status()
            posts = _extract_posts_from_rss(response.text)
            if posts:
                return posts
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise RuntimeError(f"Failed to fetch RSS feed for @{username}: {last_error}") from last_error
    return []


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

    try:
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
    except Exception:
        pass

    try:
        rss_results = _fetch_posts_from_rss(username)
        rss_seen = {post.post_id for post in results}
        for post in rss_results:
            if post.post_id in rss_seen:
                continue
            rss_seen.add(post.post_id)
            results.append(post)
    except Exception:
        pass

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
