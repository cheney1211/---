"""API routes for the chat web interface.

Provides:
  - GET  /api/health         -- health check
  - POST /api/chat           -- non-streaming REST endpoint
  - POST /api/chat/stream    -- SSE streaming endpoint
  - GET  /api/session/{id}/history -- get session history
  - DELETE /api/session/{id} -- delete session
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core import AgentMessage, AgentState
from .llm.openai_adapter import OpenAIAdapter
from .llm.provider import build_agent_provider

router = APIRouter()

_sessions: Dict[str, AgentState] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class MessageOut(BaseModel):
    role: str
    content: str


class SessionHistory(BaseModel):
    session_id: str
    messages: List[MessageOut]
    turns: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_session(session_id: str | None = None) -> tuple[str, AgentState]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    sid = session_id or str(uuid.uuid4())
    state = AgentState()
    _sessions[sid] = state
    return sid, state


def _require_env() -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return {
        "api_key": api_key,
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "base_url": os.getenv("OPENAI_BASE_URL") or None,
        "system_message": os.getenv(
            "SYSTEM_MESSAGE",
            "你叫coco，根据用户给的消息，帮助用户解决问题，语气要温和。",
        ),
    }


def _build_agent_adapter(cfg: dict) -> OpenAIAdapter:
    return OpenAIAdapter(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
    )


def _build_agent_provider(cfg: dict):
    adapter = _build_agent_adapter(cfg)
    return build_agent_provider(adapter, system_message=cfg["system_message"])


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming REST endpoint for simple request/response."""
    cfg = _require_env()
    session_id, state = _get_or_create_session(request.session_id)

    provider = _build_agent_provider(cfg)
    state.append(AgentMessage(role="user", content=request.message))

    full_text = ""
    async for msg in provider(state):
        if msg.metadata.get("chunk"):
            continue
        if msg.role == "assistant":
            full_text = msg.content
            state.append(msg)

    state.turns += 1
    _sessions[session_id] = state

    return ChatResponse(reply=full_text, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint using adapter-backed provider for rich status + token streaming.

    Event types:
      - event: session  -> {"session_id": "..."}
      - event: status   -> {"status": "thinking" | "tool_start" | "tool_end" | ...}
      - event: chunk    -> {"content": "token text"}
      - event: done     -> {"content": "full text", "session_id": "..."}
    """
    cfg = _require_env()
    session_id, state = _get_or_create_session(request.session_id)

    provider = _build_agent_provider(cfg)
    state.append(AgentMessage(role="user", content=request.message))

    async def event_generator():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}

        full_text = ""
        async for msg in provider(state):
            if msg.metadata.get("chunk"):
                full_text += msg.content
                yield {
                    "event": "chunk",
                    "data": json.dumps({"content": msg.content}),
                }
            elif msg.role == "assistant":
                full_text = msg.content
                state.append(msg)

        state.turns += 1
        _sessions[session_id] = state

        yield {
            "event": "done",
            "data": json.dumps({"content": full_text, "session_id": session_id}),
        }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.get("/session/{session_id}/history", response_model=SessionHistory)
async def get_history(session_id: str):
    if session_id not in _sessions:
        return SessionHistory(session_id=session_id, messages=[], turns=0)
    state = _sessions[session_id]
    messages = [MessageOut(role=m.role, content=m.content) for m in state.messages]
    return SessionHistory(session_id=session_id, messages=messages, turns=state.turns)


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
    return {"deleted": True, "session_id": session_id}


class SyncMessagesRequest(BaseModel):
    messages: List[MessageOut]
    turns: int


@router.put("/session/{session_id}/messages")
async def sync_messages(session_id: str, request: SyncMessagesRequest):
    """Replace the messages for a session (used after frontend-side edits/deletions)."""
    if session_id not in _sessions:
        return {"ok": False, "detail": "session not found"}
    state = _sessions[session_id]
    state.messages = [
        AgentMessage(role=m.role, content=m.content) for m in request.messages
    ]
    state.turns = request.turns
    _sessions[session_id] = state
    return {"ok": True}
