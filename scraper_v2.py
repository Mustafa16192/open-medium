import html as html_lib
import os
import re
import shutil
import subprocess
from urllib.parse import urlparse
from typing import Iterable, Optional, Tuple

import requests

try:
    import pdfkit  # type: ignore
except Exception:
    pdfkit = None

# ============= CONFIG =============
FREEDIUM_BASES = [
    os.environ.get("FREEDIUM_BASE"),
    "https://freedium.io",
    "https://freedium.cfd",
]
OUTPUT_DIR = "agent_native_articles_v2"
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


def get_freedium_url(medium_url: str) -> str:
    article_id = _extract_article_id(medium_url)
    base = next((b for b in FREEDIUM_BASES if b), "https://freedium.io")
    return f"{base.rstrip('/')}/{article_id}"


def _iter_freedium_urls(medium_url: str) -> Iterable[Tuple[str, str]]:
    article_id = _extract_article_id(medium_url)

    for base in FREEDIUM_BASES:
        if not base:
            continue
        yield base.rstrip("/"), f"{base.rstrip('/')}/{article_id}"


def _fetch_first_working_freedium_html(medium_url: str) -> Tuple[str, str]:
    last_error: Optional[BaseException] = None
    for base, freedium_url in _iter_freedium_urls(medium_url):
        print(f"-> Fetching: {freedium_url}")
        try:
            response = requests.get(
                freedium_url,
                headers=HEADERS,
                timeout=(10, 30),
            )
            response.raise_for_status()
            return freedium_url, response.text
        except requests.exceptions.RequestException as exc:
            last_error = exc
            continue

    attempted = ", ".join([b for b in FREEDIUM_BASES if b]) or "(none)"
    raise RuntimeError(f"All Freedium bases failed (attempted: {attempted}).") from last_error


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


def _render_pdf_with_chrome(url: str, pdf_path: str) -> None:
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
        f"--print-to-pdf={pdf_path}",
        "--virtual-time-budget=10000",
        url,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
            "javascript-delay": "2000",
            "load-error-handling": "ignore",
            "quiet": "",
            "dpi": 300,
            "margin-top": "15mm",
            "margin-bottom": "15mm",
            "margin-left": "10mm",
            "margin-right": "10mm",
        },
    )


def download_and_convert_to_pdf(medium_url: str) -> bool:
    try:
        freedium_url, html = _fetch_first_working_freedium_html(medium_url)

        article_id = _extract_article_id(medium_url)[:160]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", article_id).strip("._-")
        pdf_path = os.path.join(OUTPUT_DIR, f"{safe_name}.pdf")

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        try:
            _render_pdf_with_chrome(freedium_url, pdf_path)
        except Exception:
            _render_pdf_with_wkhtmltopdf(html, pdf_path)

        print(f"  Saved PDF: {pdf_path}")
        return True
    except Exception as exc:
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

    print(f"\nDone. Successfully saved {success_count}/{len(urls_to_fetch)} articles as PDFs.")
