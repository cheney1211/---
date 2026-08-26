"""API routes for the chat web interface.

Provides:
  - GET  /api/health              -- health check
  - GET  /api/sessions             -- list all sessions from DB
  - POST /api/chat                -- non-streaming REST endpoint
  - POST /api/chat/stream         -- SSE streaming endpoint
  - GET  /api/providers           -- list LLM providers
  - GET  /api/tools               -- list registered tools
  - GET  /api/skills              -- list registered skills
  - GET  /api/skills/{name}       -- skill details (with tools)
  - POST /api/skills/reload       -- reload skills from disk
  - GET  /api/session/{id}/history -- get session history
  - PUT  /api/session/{id}/messages -- sync messages after frontend edits
  - DELETE /api/session/{id}      -- delete session
  - POST /api/confirm/{id}        -- approve/reject a pending confirmation
  - GET  /api/confirm/pending     -- list pending confirmation requests
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core import AgentMessage, AgentState
from assistant.tools import get_tools, list_tools as list_all_tools, register as register_tool
from assistant.tools.builtin.call_skill import CallSkillTool, configure as configure_call_skill
from assistant.skills import (
    list_skills,
    get_skill_details,
    reload_skills,
    build_skills_system_prompt,
)
from storage.repositories import SessionRepo, MessageRepo, PendingToolRepo
from web.llm.langgraph_provider import confirmation_manager
from .llm import get_adapter, get_provider, get_default_provider_name, get_default_system_message, list_providers

logger = logging.getLogger("web.routes")

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


class SessionSummary(BaseModel):
    id: str
    title: str | None
    turns: int
    updated_at: str | None


class SkillSummary(BaseModel):
    name: str
    description: str
    tags: List[str]
    tool_names: List[str]
    version: str
    author: str


class SkillToolOut(BaseModel):
    name: str
    description: str


class SkillDetail(BaseModel):
    name: str
    description: str
    tags: List[str]
    tool_names: List[str]
    instruction: str | None = None
    version: str
    author: str
    tools: List[SkillToolOut]


class ConfirmRequest(BaseModel):
    approved: bool


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
    """Build provider with tools (including call_skill) and skill index."""
    provider_name = request.provider or get_default_provider_name()
    base_system = get_default_system_message()
    skill_index = build_skills_system_prompt()
    system_message = f"{base_system}\n\n{skill_index}" if skill_index else base_system

    # Configure call_skill tool with LLM and register it
    adapter = get_adapter(provider_name, model=request.model)
    configure_call_skill(adapter.llm, base_system)
    register_tool(CallSkillTool())

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


@router.get("/skills", response_model=List[SkillSummary])
async def skills():
    """List all registered skills."""
    return list_skills()


@router.get("/skills/{skill_name}", response_model=SkillDetail)
async def skill_detail(skill_name: str):
    """Return details for a given skill, including tool metadata."""
    try:
        detail = get_skill_details(skill_name)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    return detail


@router.post("/skills/reload")
async def skills_reload():
    """Reload all skills from disk."""
    count = reload_skills()
    return {"status": "ok", "skill_count": count}


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


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming REST endpoint."""
    session_id, state = await _get_or_create_session(
        request.session_id, provider=request.provider, model=request.model
    )

    user_msg = AgentMessage(role="user", content=request.message)
    await MessageRepo.append(session_id, user_msg, kind="user")
    state.append(user_msg)

    provider = _resolve_provider(request)

    full_text = ""
    async for msg in provider(state, session_id=session_id):
        if msg.metadata.get("chunk"):
            continue
        kind, is_chunk = _classify_and_extract(msg)
        await MessageRepo.append(session_id, msg, kind=kind, is_chunk=is_chunk)

        if kind == "tool_request" and msg.metadata.get("tool_calls"):
            for tc in msg.metadata["tool_calls"]:
                await PendingToolRepo.create(
                    session_id=session_id,
                    message_id=0,
                    call_id=tc.get("id", ""),
                    tool_name=tc["name"],
                    arguments=tc.get("args", {}),
                )
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
    """SSE streaming endpoint."""
    session_id, state = await _get_or_create_session(
        request.session_id, provider=request.provider, model=request.model
    )

    user_msg = AgentMessage(role="user", content=request.message)
    await MessageRepo.append(session_id, user_msg, kind="user")
    state.append(user_msg)

    provider = _resolve_provider(request)

    async def event_generator():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}

        full_text = ""
        async for msg in provider(state, session_id=session_id):
            status_data = msg.metadata.get("status")
            if status_data:
                yield {"event": "status", "data": json.dumps(status_data)}
                continue

            if msg.metadata.get("chunk"):
                full_text += msg.content
                yield {"event": "chunk", "data": json.dumps({"content": msg.content})}
                continue

            kind, is_chunk = _classify_and_extract(msg)
            await MessageRepo.append(session_id, msg, kind=kind, is_chunk=is_chunk)

            if kind == "tool_request" and msg.metadata.get("tool_calls"):
                for tc in msg.metadata["tool_calls"]:
                    await PendingToolRepo.create(
                        session_id=session_id,
                        message_id=0,
                        call_id=tc.get("id", ""),
                        tool_name=tc["name"],
                        arguments=tc.get("args", {}),
                    )

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

@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions():
    """Return all sessions stored in the database."""
    rows = await SessionRepo.list_all()
    return [
        SessionSummary(
            id=r.id,
            title=r.title,
            turns=r.turns,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


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
    """Replace the messages for a session (used after frontend edits/deletions)."""
    agent_msgs = [
        AgentMessage(role=m.role, content=m.content) for m in request.messages
    ]
    await MessageRepo.sync_messages(session_id, agent_msgs, request.turns)
    return {"ok": True}
