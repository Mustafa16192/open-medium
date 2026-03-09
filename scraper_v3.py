import html as html_lib
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from urllib.parse import urlparse, urlunparse
from typing import Iterable, Optional, Tuple

import requests
import urllib3

try:
    import cloudscraper  # type: ignore
except Exception:
    cloudscraper = None

try:
    import pdfkit  # type: ignore
except Exception:
    pdfkit = None

# ============= CONFIG =============
MIRROR_BASE = "https://freedium-mirror.cfd"
OUTPUT_DIR = "agent_native_articles"
INPUT_FILE = "agent_native_article_urls.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}

def _extract_article_id(medium_url: str) -> str:
    path = urlparse(medium_url).path.strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0].startswith("@"):
        return parts[1]
    return parts[-1]


def _clean_medium_url_path(url: str) -> str:
    parsed = urlparse(url)
    # Remove query parameters like ?source=...
    return parsed.path


def _iter_mirror_urls(medium_url: str) -> Iterable[Tuple[str, str]]:
    parsed = urlparse(medium_url)
    mirror_parsed = urlparse(MIRROR_BASE)
    mirror_url = urlunparse(
        (
            mirror_parsed.scheme,
            mirror_parsed.netloc,
            parsed.path,
            parsed.params,
            "",
            parsed.fragment,
        )
    )
    yield mirror_parsed.netloc, mirror_url


def _build_unverified_response(mirror_url: str) -> requests.Response:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
        return requests.get(
            mirror_url,
            headers=HEADERS,
            timeout=(10, 30),
            verify=False,
        )


def _extract_title_text(html: str) -> str:
    for pattern in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:title["\']',
        r"<title>(.*?)</title>",
        r'<h1[^>]*>(.*?)</h1>',
    ):
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            text = re.sub(r"<[^>]+>", " ", match.group(1))
            text = html_lib.unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text
    return ""


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _expected_slug_text(medium_url: str) -> str:
    article_id = _extract_article_id(medium_url).lower()
    return re.sub(r"-[0-9a-f]{12}$", "", article_id)


def _matches_expected_article(medium_url: str, html: str) -> bool:
    slug_text = _expected_slug_text(medium_url)
    title_text = _extract_title_text(html)
    if not slug_text or not title_text:
        return False

    slug_tokens = [token for token in _normalize_text(slug_text).split() if len(token) > 2]
    title_tokens = set(token for token in _normalize_text(title_text).split() if len(token) > 2)
    if not slug_tokens or not title_tokens:
        return False

    overlap = sum(1 for token in slug_tokens if token in title_tokens)
    required_overlap = min(4, max(2, len(slug_tokens) // 2))
    return overlap >= required_overlap


def _is_anti_bot_html(html: str) -> bool:
    sample = html[:15000].lower()
    title = _extract_title_text(html).lower()

    if title.startswith("just a moment") or title.startswith("attention required"):
        return True

    strong_markers = [
        "checking if the site connection is secure",
        "please enable cookies",
        "cf-browser-verification",
        "cloudflare ray id",
        "/cdn-cgi/challenge-platform/",
        "cf-chl-",
        "cf_chl_",
    ]
    return any(marker in sample for marker in strong_markers)


def _fetch_first_working_mirror_html(medium_url: str) -> Tuple[str, str]:
    last_error: Optional[BaseException] = None

    # Use cloudscraper when available to bypass Cloudflare anti-bot challenges.
    session = None
    if cloudscraper is not None:
        session = cloudscraper.create_scraper()

    for domain, mirror_url in _iter_mirror_urls(medium_url):
        print(f"-> Fetching: {mirror_url}")

        # First try normal SSL verification, then unverified.
        for verify in (True, False):
            try:
                # `cloudscraper` can fail when `verify=False` with:
                # "Cannot set verify_mode to CERT_NONE when check_hostname is enabled."
                # Keep it for normal verified requests, but use plain requests for
                # the unverified SSL fallback.
                if session and verify:
                    response = session.get(
                        mirror_url,
                        headers=HEADERS,
                        timeout=(10, 30),
                        verify=verify,
                    )
                else:
                    response = (
                        requests.get(
                            mirror_url,
                            headers=HEADERS,
                            timeout=(10, 30),
                            verify=True,
                        )
                        if verify
                        else _build_unverified_response(mirror_url)
                    )

                response.raise_for_status()

                # Simple heuristic to ensure it's not a block/captcha page
                if _is_anti_bot_html(response.text):
                    raise RuntimeError("Blocked by anti-bot protection")

                _validate_fetched_html(medium_url, response.text)
                return mirror_url, response.text
            except Exception as exc:
                last_error = exc
                # If it fails due to SSL verification, retry with unverified context.
                if isinstance(exc, (requests.exceptions.SSLError,)) or "certificate verify failed" in str(exc).lower():
                    if verify is not True:
                        # Already using unverified context; move to next mirror.
                        break
                    print(f"  SSL verify failed for {mirror_url}, retrying with unverified SSL context")
                    continue
                break

        try:
            print(f"  HTTP fetch blocked for {mirror_url}, retrying with headless Chrome DOM fetch")
            html = _fetch_html_with_chrome(mirror_url)
            if _is_anti_bot_html(html):
                raise RuntimeError("Blocked by anti-bot protection")
            _validate_fetched_html(medium_url, html)
            return mirror_url, html
        except Exception as exc:
            last_error = exc

    attempted = MIRROR_BASE
    raise RuntimeError(f"All mirror bases failed (attempted: {attempted}). Last error: {last_error}") from last_error


def _validate_fetched_html(medium_url: str, html: str) -> None:
    sample = html[:15000].lower()
    title = _extract_title_text(html).lower()

    known_bad_markers = [
        "pin up casino india",
        "pin up online casino",
        "get 25000 inr",
        "1win",
        "mostbet",
        "melbet",
        "betwinner",
    ]
    if any(marker in title or marker in sample for marker in known_bad_markers):
        raise RuntimeError("Fetched HTML is a betting/spam page, not the requested article.")

    if "enter medium post link" in sample and "freedium" in sample:
        raise RuntimeError("Fetched HTML is the generic Freedium landing page, not an article page.")

    if not _matches_expected_article(medium_url, html):
        raise RuntimeError(
            "Fetched HTML does not appear to match the requested article title."
        )


def _find_chrome_executable() -> Optional[str]:
    env_path = os.environ.get("CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _render_pdf_with_chrome(target: str, pdf_path: str) -> None:
    chrome = _find_chrome_executable()
    if not chrome:
        raise RuntimeError(
            "Chrome/Chromium not found. Set CHROME_PATH or install Google Chrome."
        )

    os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_path}",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=30000",  # Increased wait for full load
        "--window-size=1280,10000",     # Tall window to capture long pages
        target,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _fetch_html_with_chrome(url: str) -> str:
    chrome = _find_chrome_executable()
    if not chrome:
        raise RuntimeError(
            "Chrome/Chromium not found. Set CHROME_PATH or install Google Chrome."
        )

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=25000",
        "--window-size=1280,10000",
        f"--user-agent={HEADERS['User-Agent']}",
        "--dump-dom",
        url,
    ]
    result = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout


def _render_pdf_with_wkhtmltopdf(html: str, pdf_path: str) -> None:
    if not pdfkit:
        raise RuntimeError("pdfkit is not installed.")
    if not shutil.which("wkhtmltopdf"):
        raise RuntimeError("wkhtmltopdf is not installed.")

    pdfkit.from_string(
        html,
        pdf_path,
        options={
            "encoding": "UTF-8",
            "enable-local-file-access": "",
            "javascript-delay": "5000",  # Increased delay for JS load
            "load-error-handling": "ignore",
            "no-stop-slow-scripts": "",
            "quiet": "",
            "dpi": 300,
            "margin-top": "15mm",
            "margin-bottom": "15mm",
            "margin-left": "10mm",
            "margin-right": "10mm",
            "page-size": "A4",
            "footer-center": "[page]/[topage]",
        },
    )


def _render_pdf_from_html_with_chrome(html: str, pdf_path: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    try:
        _render_pdf_with_chrome(f"file://{tmp_path}", pdf_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _verify_pdf_content(pdf_path: str) -> None:
    if not os.path.exists(pdf_path):
        raise RuntimeError(f"PDF was not created: {pdf_path}")

    if not shutil.which("pdftotext"):
        return

    result = subprocess.run(
        ["pdftotext", pdf_path, "-"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    sample = result.stdout[:12000].lower()
    bad_markers = [
        "pin up casino india",
        "pin up online casino",
        "get 25000 inr",
        "official casino",
        "bonus for new player",
    ]
    if any(marker in sample for marker in bad_markers):
        raise RuntimeError("Generated PDF contains betting/spam content instead of the requested article.")


def download_and_convert_to_pdf(medium_url: str, output_dir: Optional[str] = None) -> bool:
    try:
        _mirror_url, html = _fetch_first_working_mirror_html(medium_url)

        article_id = _extract_article_id(medium_url)[:160]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", article_id).strip("._-")
        resolved_output_dir = output_dir or OUTPUT_DIR
        pdf_path = os.path.join(resolved_output_dir, f"{safe_name}.pdf")

        os.makedirs(resolved_output_dir, exist_ok=True)

        try:
            _render_pdf_from_html_with_chrome(html, pdf_path)
        except Exception as e:
            print(f"  Chrome rendering failed: {e}. Falling back to wkhtmltopdf.")
            _render_pdf_with_wkhtmltopdf(html, pdf_path)

        _verify_pdf_content(pdf_path)
        print(f"  Saved full PDF: {pdf_path}")
        return True
    except Exception as exc:
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        print(f"  Error on {medium_url}: {str(exc)}")
        return False


def get_urls_from_file(filepath: str) -> list[str]:
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return urls


if __name__ == "__main__":
    urls_to_fetch = get_urls_from_file(INPUT_FILE)
    
    if not urls_to_fetch:
        print(f"No URLs to process. Please check {INPUT_FILE}.")
        exit(1)

    print(f"Saving articles to: ./{OUTPUT_DIR}\n")
    print(f"Found {len(urls_to_fetch)} articles in {INPUT_FILE}.\n")

    success_count = 0
    for url in urls_to_fetch:
        if download_and_convert_to_pdf(url):
            success_count += 1

    print(f"\nDone. Successfully saved {success_count}/{len(urls_to_fetch)} articles as full PDFs (with text and images).")
