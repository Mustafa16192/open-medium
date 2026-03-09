# Medium Articles to PDF Scraper

## Project Overview
This project provides a Python script to make the author's own Medium articles more accessible by converting them into PDF format. It works by routing the provided Medium article URLs through an alternative service (Freedium) and then rendering the resulting page as a PDF file, complete with text and images.

**Key Features:**
- **URL Routing:** Takes a list of Medium URLs and dynamically constructs Freedium mirror URLs to bypass access barriers and ensure accessibility.
- **PDF Generation:** Downloads the rendered article page and saves it as a PDF. The tool primarily tries to use headless Google Chrome for high-quality rendering. If Chrome fails or isn't present, it falls back to using `wkhtmltopdf` (via `pdfkit`).
- **Batch Processing:** Processes a hardcoded or configured list of article URLs in one go, saving all the resulting PDFs into a structured output directory (`agent_native_articles/`).

## Directory Structure
- `scraper.py`: The main Python script that handles the downloading and PDF conversion.
- `agent_native_article_urls.txt`: Contains URLs of the target Medium articles.
- `requirements.txt`: Python package dependencies.
- `agent_native_articles/`: The default output directory where the generated PDF files are saved.

## Building and Running

### Setup
Ensure you have Python 3 installed. Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

**System Dependencies:**
To render the PDFs, the script requires a browser or rendering engine to be installed on your system:
1. **Google Chrome / Chromium:** The script will attempt to find Chrome automatically (or you can specify its location using the `CHROME_PATH` environment variable). This is the preferred method.
2. **wkhtmltopdf:** If Chrome is unavailable, the script will fall back to `pdfkit`, which requires `wkhtmltopdf` to be installed on your system (e.g., `brew install wkhtmltopdf` on macOS or `apt-get install wkhtmltopdf` on Debian/Ubuntu).

### Usage Example
Run the main script to start processing the articles:

```bash
python3 scraper.py
```

The script will fetch each URL, attempt the conversion, print its progress to the terminal, and save the successful `.pdf` files to the `agent_native_articles/` directory.

## Development Conventions
- **Fallback Mechanisms:** The script is designed with resilience in mind. It iterates through multiple Freedium base URLs to find a working mirror and gracefully falls back between rendering engines (Chrome -> wkhtmltopdf) to maximize the chances of successful PDF generation.
- **Environment Variables:** `FREEDIUM_BASE` can be set to override or prepend to the list of base mirror URLs. `CHROME_PATH` can be set to explicitly point to a Chrome/Chromium executable.
