"""API routes for the chat web interface.

Provides:
  - GET  /api/health              -- health check
  - POST /api/chat                -- non-streaming REST endpoint
  - POST /api/chat/stream         -- SSE streaming endpoint
  - GET  /api/providers           -- list LLM providers
  - GET  /api/tools               -- list registered tools
  - GET  /api/session/{id}/history -- get session history
  - PUT  /api/session/{id}/messages -- sync messages after frontend edits
  - DELETE /api/session/{id}      -- delete session
"""

from __future__ import annotations

import json
import uuid
from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core import AgentMessage, AgentState
from assistant.tools import get_tools, list_tools as list_all_tools
from storage.repositories import SessionRepo, MessageRepo, PendingToolRepo
from .llm import get_provider, get_default_provider_name, get_default_system_message, list_providers

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

async def _get_or_create_session(
    session_id: str | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, AgentState]:
    """Return (session_id, AgentState) backed by DB."""
    sid = session_id or str(uuid.uuid4())
    await SessionRepo.get_or_create(sid, provider=provider, model=model)
    messages = await MessageRepo.list_recent(sid)
    turns = await MessageRepo.get_turns(sid)
    state = AgentState(messages=messages, turns=turns)
    return sid, state


def _resolve_provider(request: ChatRequest):
    """Resolve provider name and build an agent-ready provider from the registry."""
    provider_name = request.provider or get_default_provider_name()
    system_message = get_default_system_message()
    tools = get_tools()
    return get_provider(
        provider_name,
        model=request.model,
        system_message=system_message,
        tools=tools,
    )


def _classify_and_extract(msg: AgentMessage) -> tuple[str, bool]:
    """Return (kind, is_chunk) for a given AgentMessage."""
    if msg.metadata.get("chunk"):
        return "status", True
    if msg.role == "tool":
        return "tool_result", False
    if msg.metadata.get("tool_calls"):
        return "tool_request", False
    return msg.role if msg.role in ("user", "assistant", "system") else "user", False


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/providers")
async def providers():
    """List all registered LLM providers."""
    return {
        "default": get_default_provider_name(),
        "providers": list_providers(),
    }


@router.get("/tools")
async def tools():
    """List all registered tools."""
    return {"tools": list_all_tools()}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming REST endpoint for simple request/response."""
    session_id, state = await _get_or_create_session(
        request.session_id, provider=request.provider, model=request.model
    )

    # Persist user message
    user_msg = AgentMessage(role="user", content=request.message)
    await MessageRepo.append(session_id, user_msg, kind="user")
    state.append(user_msg)

    provider = _resolve_provider(request)

    full_text = ""
    async for msg in provider(state):
        if msg.metadata.get("chunk"):
            continue

        kind, is_chunk = _classify_and_extract(msg)

        # Persist to DB
        db_row = await MessageRepo.append(session_id, msg, kind=kind, is_chunk=is_chunk)

        # If this is a tool_request, register pending calls
        if kind == "tool_request" and msg.metadata.get("tool_calls"):
            for tc in msg.metadata["tool_calls"]:
                await PendingToolRepo.create(
                    session_id=session_id,
                    message_id=db_row.id,
                    call_id=tc.get("id", ""),
                    tool_name=tc["name"],
                    arguments=tc.get("args", {}),
                )

        # If this is a tool_result, mark corresponding pending as done
        if kind == "tool_result":
            tcid = msg.metadata.get("tool_call_id", "")
            if tcid:
                pendings = await PendingToolRepo.list_resumable(session_id)
                for p in pendings:
                    if p.call_id == tcid and p.status in ("queued", "running"):
                        await PendingToolRepo.mark_done(p.id)

        state.append(msg)
        if msg.role == "assistant":
            full_text = msg.content

    state.turns += 1
    await SessionRepo.set_turns(session_id, state.turns)

    return ChatResponse(reply=full_text, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint.

    Event types:
      - event: session  -> {"session_id": "..."}
      - event: status   -> {"status": "thinking" | "tool_start" | "tool_end" | ...}
      - event: chunk    -> {"content": "token text"}
      - event: done     -> {"content": "full text", "session_id": "..."}
    """
    session_id, state = await _get_or_create_session(
        request.session_id, provider=request.provider, model=request.model
    )

    # Persist user message
    user_msg = AgentMessage(role="user", content=request.message)
    await MessageRepo.append(session_id, user_msg, kind="user")
    state.append(user_msg)

    provider = _resolve_provider(request)

    async def event_generator():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}

        full_text = ""
        async for msg in provider(state):
            status_data = msg.metadata.get("status")
            if status_data:
                # Forward status event to frontend but don't persist
                yield {
                    "event": "status",
                    "data": json.dumps(status_data),
                }
                continue

            if msg.metadata.get("chunk"):
                full_text += msg.content
                yield {
                    "event": "chunk",
                    "data": json.dumps({"content": msg.content}),
                }
                continue

            # --- Non-chunk: classify, persist, handle tool lifecycle ---
            kind, is_chunk = _classify_and_extract(msg)
            db_row = await MessageRepo.append(
                session_id, msg, kind=kind, is_chunk=is_chunk
            )

            # tool_request -> create pending
            if kind == "tool_request" and msg.metadata.get("tool_calls"):
                for tc in msg.metadata["tool_calls"]:
                    await PendingToolRepo.create(
                        session_id=session_id,
                        message_id=db_row.id,
                        call_id=tc.get("id", ""),
                        tool_name=tc["name"],
                        arguments=tc.get("args", {}),
                    )

            # tool_result -> mark pending done
            if kind == "tool_result":
                tcid = msg.metadata.get("tool_call_id", "")
                if tcid:
                    pendings = await PendingToolRepo.list_resumable(session_id)
                    for p in pendings:
                        if p.call_id == tcid and p.status in ("queued", "running"):
                            await PendingToolRepo.mark_done(p.id)

            state.append(msg)
            if msg.role == "assistant":
                full_text = msg.content

        state.turns += 1
        await SessionRepo.set_turns(session_id, state.turns)

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
    messages = await MessageRepo.list_recent(session_id)
    turns = await MessageRepo.get_turns(session_id)
    out = [MessageOut(role=m.role, content=m.content) for m in messages]
    return SessionHistory(session_id=session_id, messages=out, turns=turns)


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    deleted = await SessionRepo.delete(session_id)
    return {"deleted": deleted, "session_id": session_id}


class SyncMessagesRequest(BaseModel):
    messages: List[MessageOut]
    turns: int


@router.put("/session/{session_id}/messages")
async def sync_messages(session_id: str, request: SyncMessagesRequest):
    """Replace the messages for a session (used after frontend-side edits/deletions)."""
    agent_msgs = [
        AgentMessage(role=m.role, content=m.content) for m in request.messages
    ]
    await MessageRepo.sync_messages(session_id, agent_msgs, request.turns)
    return {"ok": True}


