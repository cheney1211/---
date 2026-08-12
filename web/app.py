"""FastAPI application for the chat web interface."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router as chat_router

# Load .env from project root
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="xiaozhushou", version="0.2.0")

    # CORS: allow Next.js dev server and common local ports
    # Use permissive settings for local development to avoid preflight failures.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(chat_router, prefix="/api")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
