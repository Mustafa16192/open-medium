# open-medium

Web app and CLI scraper for discovering Medium articles in a date range and exporting them to PDF through the Freedium mirror pipeline.

## Project Layout

- `api.py`: FastAPI backend that launches the scraper and exposes download endpoints
- `frontend/`: Next.js app for entering a Medium profile and date range
- `medium_user_range_scraper.py`: CLI entrypoint for direct scraping runs
- `scraper_v3.py`: mirror fetch, validation, and PDF rendering pipeline
- `MEDIUM_USER_RANGE_SCRAPER_USAGE.md`: CLI usage guide
- `SCRAPER_V3_REPLICATION_SPEC.md`: pipeline behavior and debugging notes

## Run The Web App

### Backend

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Start the API:

```bash
python3 api.py
```

Backend URL:

```text
http://127.0.0.1:8001
```

API docs:

```text
http://127.0.0.1:8001/docs
```

If your Python environment is running under Rosetta on Apple Silicon, use:

```bash
arch -arm64 python3 api.py
```

### Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

If the backend runs on a different port:

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002 npm run dev
```

If the backend needs a different port:

```bash
UVICORN_HOST=127.0.0.1 UVICORN_PORT=8002 python3 api.py
```

## Use The UI

- paste a Medium profile URL or handle
- choose a start and end date
- run the conversion
- download the resulting PDFs or the ZIP archive

## Run The CLI Scraper

Use this if you want direct terminal scraping without the web app:

```bash
python3 medium_user_range_scraper.py \
  --username agentnativedev \
  --start-date 2026-02-01 \
  --end-date 2026-03-09 \
  --output-dir agent_native_articles_range \
  --save-url-list
```

## API Endpoints

- `POST /api/convert`
- `GET /api/files`
- `GET /api/download/{filename}`
- `GET /api/download-all`

## Output

Generated PDFs are written to the output directory you pass in. The web app defaults to `agent_native_articles/`.

## Generated Files

Keep these out of commits:

- `agent_native_articles/`
- `agent_native_articles_v3/`
- `verified/`
- `tmp_test/`
- `frontend/.next/`
- `frontend/node_modules/`
