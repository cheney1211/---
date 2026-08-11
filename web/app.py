"""FastAPI application for the chat web interface."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import router as chat_router

# Load .env from project root
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="小助手", version="0.1.0")

    # Register API routes
    app.include_router(chat_router, prefix="/api")

    # Serve static files (frontend)
    _static = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(_static / "index.html"))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
