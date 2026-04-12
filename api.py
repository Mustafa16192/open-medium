import asyncio
import os
import json
import logging
import sys
import shutil
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Medium to PDF API")
OUTPUT_DIR = Path("agent_native_articles")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConvertRequest(BaseModel):
    username: str
    start_date: str
    end_date: str


def _reset_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for entry in OUTPUT_DIR.iterdir():
        if entry.is_file() and entry.suffix.lower() in {".pdf", ".txt"}:
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)

@app.post("/api/convert")
async def convert_urls(req: ConvertRequest, request: Request):
    """
    Accepts a username and date range and starts the scraper.
    Returns a Server-Sent Events (SSE) stream of progress logs.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            _reset_output_dir()

            # 2. Run the scraper process
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"  # Ensure stdout is unbuffered

            cmd = [
                sys.executable, "medium_user_range_scraper.py",
                "--username", req.username,
                "--start-date", req.start_date,
                "--end-date", req.end_date,
                "--output-dir", str(OUTPUT_DIR)
            ]
            
            logger.info(f"Running command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            # 3. Read stdout line by line and yield as SSE
            if process.stdout:
                while True:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        process.terminate()
                        break
                        
                    line = await process.stdout.readline()
                    if not line:
                        break
                        
                    log_line = line.decode('utf-8').rstrip()
                    if log_line:
                        logger.info(f"Scraper: {log_line}")
                        yield json.dumps({"type": "log", "message": log_line})
            
            await process.wait()
            yield json.dumps({"type": "done", "status": process.returncode})
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            yield json.dumps({"type": "error", "message": str(e)})

    return EventSourceResponse(event_generator())


@app.get("/api/files")
async def list_files():
    """Returns a list of generated PDF files."""
    output_dir = OUTPUT_DIR
    if not output_dir.exists():
        return {"files": []}
    
    files = [f.name for f in output_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
    # Sort by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(output_dir / x), reverse=True)
    return {"files": files}


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Serves a specific PDF file."""
    file_path = OUTPUT_DIR / filename
    if file_path.exists():
        return FileResponse(path=str(file_path), filename=filename, media_type='application/pdf')
    return {"error": "File not found"}

import zipfile
import io
from fastapi.responses import StreamingResponse

@app.get("/api/download-all")
async def download_all():
    """Serves all PDF files as a ZIP archive."""
    if not OUTPUT_DIR.exists():
        return {"error": "No files found"}
        
    pdf_files = list(OUTPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        return {"error": "No files found"}
        
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in pdf_files:
            zip_file.write(file_path, file_path.name)
            
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=articles.zip"}
    )

if __name__ == "__main__":
    import uvicorn
    reload_enabled = os.getenv("UVICORN_RELOAD", "0") == "1"
    host = os.getenv("UVICORN_HOST", "127.0.0.1")
    port = int(os.getenv("UVICORN_PORT", "8001"))
    uvicorn.run("api:app", host=host, port=port, reload=reload_enabled)
