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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from assistant.core import AgentMessage, AgentState

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


def _to_lc_messages(messages: list[AgentMessage], system_message: str) -> list:
    lc = [SystemMessage(content=system_message)]
    for m in messages:
        if m.role == "user":
            lc.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            lc.append(AIMessage(content=m.content))
    return lc


def _build_llm(api_key: str, model: str, base_url: str | None) -> ChatOpenAI:
    kw = {"model": model, "api_key": api_key, "temperature": 0.7, "streaming": True}
    if base_url:
        kw["base_url"] = base_url
    return ChatOpenAI(**kw)


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

    llm = _build_llm(cfg["api_key"], cfg["model"], cfg["base_url"])
    state.append(AgentMessage(role="user", content=request.message))

    lc_msgs = _to_lc_messages(state.messages, cfg["system_message"])
    response = await llm.ainvoke(lc_msgs)
    reply = response.content

    state.append(AgentMessage(role="assistant", content=reply))
    state.turns += 1
    _sessions[session_id] = state

    return ChatResponse(reply=reply, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint using astream_events for rich status + token streaming.

    Event types:
      - event: session  -> {"session_id": "..."}
      - event: status   -> {"status": "thinking" | "tool_start" | "tool_end" | ...}
      - event: chunk    -> {"content": "token text"}
      - event: done     -> {"content": "full text", "session_id": "..."}
    """
    cfg = _require_env()
    session_id, state = _get_or_create_session(request.session_id)

    llm = _build_llm(cfg["api_key"], cfg["model"], cfg["base_url"])
    state.append(AgentMessage(role="user", content=request.message))

    lc_msgs = _to_lc_messages(state.messages, cfg["system_message"])

    async def event_generator():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}

        full_text_parts: list[str] = []

        async for event in llm.astream_events(lc_msgs, version="v2"):
            kind = event["event"]

            if kind == "on_chat_model_start":
                yield {
                    "event": "status",
                    "data": json.dumps({"status": "thinking"}),
                }

            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    token = chunk.content or ""
                    if token:
                        full_text_parts.append(token)
                        yield {
                            "event": "chunk",
                            "data": json.dumps({"content": token}),
                        }

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                yield {
                    "event": "status",
                    "data": json.dumps({"status": "tool_start", "name": tool_name}),
                }

            elif kind == "on_tool_end":
                yield {
                    "event": "status",
                    "data": json.dumps({"status": "tool_end"}),
                }

            elif kind == "on_retriever_start":
                yield {
                    "event": "status",
                    "data": json.dumps({"status": "retriever_start"}),
                }

            elif kind == "on_retriever_end":
                yield {
                    "event": "status",
                    "data": json.dumps({"status": "retriever_end"}),
                }

        full_text = "".join(full_text_parts)
        state.append(AgentMessage(role="assistant", content=full_text))
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
