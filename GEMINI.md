# open-medium: Medium Articles to PDF Scraper

## Project Overview
This project, "open-medium", provides a complete pipeline to discover a Medium user's articles within a specific date range and export them as full PDF files. It bypasses paywalls by routing Medium URLs through the Freedium mirror service (`freedium-mirror.cfd`), renders the resulting pages using headless Chrome (or `wkhtmltopdf` as a fallback), and provides both a CLI and a Web UI for users.

**Key Features:**
- **URL Discovery & Routing:** Scrapes a user's profile or archive for articles within a date range and constructs Freedium mirror URLs.
- **Validation Pipeline:** Employs multiple validation stages (HTML validation, title matching, and PDF text verification via `pdftotext`) to reject spam, bypass captchas, and ensure accuracy.
- **PDF Generation:** High-quality PDF rendering of articles using headless Google Chrome.
- **FastAPI Backend:** Provides REST endpoints (`/api/convert`, `/api/files`, `/api/download`) and uses Server-Sent Events (SSE) to stream scraper logs in real-time.
- **Next.js Frontend:** A modern React-based web interface to easily input parameters (username, date range) and download the generated PDFs.

## Directory Structure
- `medium_user_range_scraper.py`: End-to-end CLI script that coordinates the discovery and downloading of a user's articles.
- `scraper_v3.py`: The core mirror-based fetch, validation, and PDF rendering pipeline.
- `api.py`: FastAPI application serving the frontend and managing scraper execution.
- `frontend/`: Next.js web application providing the user interface.
- `requirements.txt`: Python package dependencies.
- `agent_native_articles/`: Default output directory for generated PDF files.
- `MEDIUM_USER_RANGE_SCRAPER_USAGE.md`: Detailed usage guide for the CLI.
- `SCRAPER_V3_REPLICATION_SPEC.md`: Replication spec and debugging history for the scraper pipeline.

## Building and Running

### Setup
Ensure you have Python 3 and Node.js installed.

**Backend Dependencies:**
```bash
pip install -r requirements.txt
```

**Frontend Dependencies:**
```bash
cd frontend
npm install
```

**System Dependencies:**
- Google Chrome or Chromium (highly recommended for rendering).
- `pdftotext` (for PDF text validation).
- `wkhtmltopdf` (as a fallback renderer).

### Usage

**Running the Web App:**
1. Start the FastAPI backend:
   ```bash
   python3 api.py
   ```
2. Start the Next.js frontend:
   ```bash
   cd frontend
   npm run dev
   ```

**Running via CLI:**
```bash
python3 medium_user_range_scraper.py \
  --username <username> \
  --start-date <YYYY-MM-DD> \
  --end-date <YYYY-MM-DD> \
  --output-dir agent_native_articles \
  --save-url-list
```

## Development Conventions
- **Resilience & Validation:** The scraper explicitly validates fetched content to catch false positives or rate-limit blocks from the mirror.
- **SSE for Logs:** Long-running scraping tasks stream their output back to the frontend using Server-Sent Events to provide real-time user feedback.
- **Output Management:** The API automatically cleans up the output directory before starting a new conversion task to avoid mixing files.