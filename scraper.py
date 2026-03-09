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
OUTPUT_DIR = "agent_native_articles"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
}

ARTICLE_URLS = [
    "https://medium.com/@agentnativedev/monetize-openai-gpts-use-cases-and-strategies-3cbee026a0d5",
    "https://medium.com/@agentnativedev/mcp-toolbox-google-grade-database-tooling-for-llm-agents-013fe802a53b",
    "https://medium.com/@agentnativedev/fully-local-rag-with-qdrant-ollama-langchain-and-langserve-10d4dd1facbc",
    "https://medium.com/@agentnativedev/local-copy-of-chatgpt-and-gpt-4-vision-llamafile-175891b27e95",
    "https://medium.com/@agentnativedev/ask-py-perplexity-like-search-extract-summarize-flow-in-python-715e13eff07f",
    "https://medium.com/@agentnativedev/chain-of-density-for-effective-text-summarization-with-large-language-models-ddddf44d8040",
    "https://medium.com/@agentnativedev/efficient-content-moderation-for-text-to-image-models-promptguard-and-safety-embeddings-04bb1e3121e9",
    "https://medium.com/@agentnativedev/why-mark-zuckerbergs-relentless-urgency-in-acquiring-instagram-is-a-masterclass-for-entrepreneurs-41162133d362",
    "https://medium.com/@agentnativedev/googles-gemini-is-forcing-openai-s-hand-with-gpt-5-your-move-apple-1b6398774d61",
    "https://medium.com/@agentnativedev/inside-openais-devday-gpt-4-turbo-gpts-assistants-api-and-the-future-of-humanity-6b34368eeb24",
    "https://medium.com/@agentnativedev/orca-2-vs-gpt-4-the-smaller-smarter-llm-is-redefining-reasoning-and-strategy-9dae1d2085fd",
    "https://medium.com/@agentnativedev/hugging-faces-unified-api-standardizing-tool-use-across-top-ai-models-from-mistral-cohere-nous-2210bdb4f2a7",
    "https://medium.com/@agentnativedev/latest-vision-image-and-language-models-pangea-ferret-omniparser-granite-pixtral-aya-sd-3-5-e8d6e3555ee2",
]


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

        print(f"  Saved PDF: {pdf_path} (includes text and images)")
        return True
    except Exception as exc:
        print(f"  Error on {medium_url}: {str(exc)}")
        return False


if __name__ == "__main__":
    print(f"Saving all Agent Native articles to: ./{OUTPUT_DIR}\n")
    print(f"Found {len(ARTICLE_URLS)} articles.\n")

    success_count = 0
    for url in ARTICLE_URLS:
        if download_and_convert_to_pdf(url):
            success_count += 1

    print(f"\nDone. Successfully saved {success_count}/{len(ARTICLE_URLS)} articles as PDFs.")
