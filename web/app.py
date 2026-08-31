"""FastAPI application for the chat web interface."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router as chat_router
from storage import init_db, recover_pending_tool_calls, get_engine

# Load .env from project root
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

logger = logging.getLogger("web.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # ---- startup ----
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    await init_db()
    recovered = await recover_pending_tool_calls()
    if recovered:
        logger.warning(
            "Recovered %d pending tool call(s) -> marked as error (manual retry needed)",
            len(recovered),
        )
    logger.info("Database ready")
    yield
    # ---- shutdown ----
    from web.llm.langgraph_provider import LangGraphProvider
    await LangGraphProvider.close_all()
    engine = get_engine()
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="xiaozhushou", version="0.3.0", lifespan=lifespan)

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

    # Exclude workspace and data dirs from reload watcher so that
    # tool-generated file writes don't restart the dev server.
    _reload_excludes = [
        "data/*",
        "frontend/*",
        ".venv/*",
        ".next/*",
    ]
    _workspace = os.getenv("WORKSPACE_ROOT")
    if _workspace:
        _reload_excludes.append(os.path.join(_workspace, "*"))

    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=_reload_excludes,
    )
