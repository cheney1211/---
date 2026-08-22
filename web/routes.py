"""API routes for the chat web interface.

Provides:
  - GET  /api/health              -- health check
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
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core import AgentMessage, AgentState
from assistant.tools import get_tools, list_tools as list_all_tools
from assistant.tools.builtin.call_skill import SKILL_ROUTING_PREFIX
from assistant.skills import (
    list_skills,
    get_skill_details,
    get_skill,
    reload_skills,
    build_skills_system_prompt,
    build_skill_instruction_prompt,
)
from storage.repositories import SessionRepo, MessageRepo, PendingToolRepo
from .llm import get_provider, get_default_provider_name, get_default_system_message, list_providers

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
    """Resolve provider with skill index injected into system message."""
    provider_name = request.provider or get_default_provider_name()
    base_system = get_default_system_message()
    skill_index = build_skills_system_prompt()
    system_message = f"{base_system}\n\n{skill_index}" if skill_index else base_system
    tools = get_tools()
    return get_provider(
        provider_name,
        model=request.model,
        system_message=system_message,
        tools=tools,
    )


def _build_skill_provider(request: ChatRequest, skill_name: str):
    """Build a provider for the second LLM call with full skill instruction."""
    provider_name = request.provider or get_default_provider_name()
    base_system = get_default_system_message()
    skill_prompt = build_skill_instruction_prompt(skill_name)
    system_message = f"{base_system}\n\n{skill_prompt}"
    # No tools in second call - pure text generation
    return get_provider(
        provider_name,
        model=request.model,
        system_message=system_message,
        tools=[],
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


def _detect_skill_routing(state: AgentState) -> str | None:
    """Check if the last tool result is a skill routing call. Returns skill name or None."""
    for msg in reversed(state.messages):
        if msg.role == "tool" and msg.content.startswith(SKILL_ROUTING_PREFIX):
            return msg.content[len(SKILL_ROUTING_PREFIX):].strip()
    return None


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


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming REST endpoint with two-phase skill routing."""
    session_id, state = await _get_or_create_session(
        request.session_id, provider=request.provider, model=request.model
    )

    # Persist user message
    user_msg = AgentMessage(role="user", content=request.message)
    await MessageRepo.append(session_id, user_msg, kind="user")
    state.append(user_msg)

    # --- Phase 1: LLM call with skill index ---
    provider = _resolve_provider(request)

    full_text = ""
    async for msg in provider(state):
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

    # --- Phase 2: Check if skill routing was triggered ---
    skill_name = _detect_skill_routing(state)
    if skill_name:
        logger.info("Skill routing detected: %s", skill_name)
        try:
            skill_provider = _build_skill_provider(request, skill_name)
        except ValueError:
            pass
        else:
            full_text = ""
            async for msg in skill_provider(state):
                if msg.metadata.get("chunk"):
                    continue
                kind, is_chunk = _classify_and_extract(msg)
                await MessageRepo.append(session_id, msg, kind=kind, is_chunk=is_chunk)
                state.append(msg)
                if msg.role == "assistant":
                    full_text = msg.content

    state.turns += 1
    await SessionRepo.set_turns(session_id, state.turns)

    return ChatResponse(reply=full_text, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint with two-phase skill routing."""
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
        async for msg in provider(state):
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

        # --- Phase 2: skill routing ---
        skill_name = _detect_skill_routing(state)
        if skill_name:
            logger.info("Skill routing detected (stream): %s", skill_name)
            yield {
                "event": "status",
                "data": json.dumps({"status": "skill_routing", "skill": skill_name}),
            }
            try:
                skill_provider = _build_skill_provider(request, skill_name)
            except ValueError:
                pass
            else:
                full_text = ""
                async for msg in skill_provider(state):
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
