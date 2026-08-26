"""Chat and confirmation routes."""

from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from web.llm.langgraph_provider import confirmation_manager
from web.services.chat_service import get_or_create_session, process_message, process_message_stream

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    provider: str | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class ConfirmRequest(BaseModel):
    approved: bool


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming REST endpoint."""
    session_id, state = await get_or_create_session(
        request.session_id, provider=request.provider, model=request.model,
    )
    reply = await process_message(
        session_id, state, request.message,
        provider=request.provider, model=request.model,
    )
    return ChatResponse(reply=reply, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint."""
    session_id, state = await get_or_create_session(
        request.session_id, provider=request.provider, model=request.model,
    )

    async def event_generator():
        async for event in process_message_stream(
            session_id, state, request.message,
            provider=request.provider, model=request.model,
        ):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Confirmation endpoints
# ---------------------------------------------------------------------------

@router.post("/confirm/{confirmation_id}")
async def confirm_tool(confirmation_id: str, request: ConfirmRequest):
    """Approve or reject a pending tool confirmation."""
    found = confirmation_manager.resolve(confirmation_id, request.approved)
    if not found:
        return JSONResponse(
            status_code=404,
            content={"error": f"Confirmation request '{confirmation_id}' not found or already resolved"},
        )
    return {
        "status": "resolved",
        "confirmation_id": confirmation_id,
        "approved": request.approved,
    }


@router.get("/confirm/pending")
async def list_pending_confirmations():
    """List all pending confirmation requests."""
    return {"pending": confirmation_manager.list_pending()}
