"""Chat service — orchestrates session, message, and provider logic."""

from __future__ import annotations

import uuid
from typing import AsyncIterable

from assistant.core import AgentMessage, AgentState
from assistant.tools import get_tools, register as register_tool
from assistant.tools.builtin.call_skill import CallSkillTool, configure as configure_call_skill
from assistant.skills import build_skills_system_prompt
from storage.repositories import SessionRepo, MessageRepo, PendingToolRepo
from web.llm import get_adapter, get_provider, get_default_provider_name, get_default_system_message
from web.utils.message_utils import classify_and_extract


async def get_or_create_session(
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


def resolve_provider(*, provider: str | None = None, model: str | None = None):
    """Build provider with tools (including call_skill) and skill index."""
    provider_name = provider or get_default_provider_name()
    base_system = get_default_system_message()
    skill_index = build_skills_system_prompt()
    system_message = f"{base_system}\n\n{skill_index}" if skill_index else base_system

    adapter = get_adapter(provider_name, model=model)
    configure_call_skill(adapter.llm, base_system)
    register_tool(CallSkillTool())

    tools = get_tools()
    return get_provider(provider_name, model=model, system_message=system_message, tools=tools)


async def persist_message(session_id: str, msg: AgentMessage, *, kind: str = "user") -> None:
    """Write one message and track pending tool calls."""
    await MessageRepo.append(session_id, msg, kind=kind)

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


async def process_message(
    session_id: str,
    state: AgentState,
    user_text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Non-streaming: persist user msg, run provider, persist all responses, return reply."""
    user_msg = AgentMessage(role="user", content=user_text)
    await persist_message(session_id, user_msg, kind="user")
    state.append(user_msg)

    llm_provider = resolve_provider(provider=provider, model=model)

    full_text = ""
    async for msg in llm_provider(state, session_id=session_id):
        if msg.metadata.get("chunk"):
            continue
        kind, is_chunk = classify_and_extract(msg)
        await persist_message(session_id, msg, kind=kind)
        state.append(msg)
        if msg.role == "assistant":
            full_text = msg.content

    state.turns += 1
    await SessionRepo.set_turns(session_id, state.turns)
    return full_text


async def process_message_stream(
    session_id: str,
    state: AgentState,
    user_text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> AsyncIterable[dict]:
    """Streaming: yields SSE event dicts (session / status / chunk / done)."""
    user_msg = AgentMessage(role="user", content=user_text)
    await persist_message(session_id, user_msg, kind="user")
    state.append(user_msg)

    llm_provider = resolve_provider(provider=provider, model=model)

    yield {"event": "session", "data": {"session_id": session_id}}

    full_text = ""
    async for msg in llm_provider(state, session_id=session_id):
        status_data = msg.metadata.get("status")
        if status_data:
            yield {"event": "status", "data": status_data}
            continue

        if msg.metadata.get("chunk"):
            full_text += msg.content
            yield {"event": "chunk", "data": {"content": msg.content}}
            continue

        kind, is_chunk = classify_and_extract(msg)
        await persist_message(session_id, msg, kind=kind)
        state.append(msg)
        if msg.role == "assistant":
            full_text = msg.content

    state.turns += 1
    await SessionRepo.set_turns(session_id, state.turns)
    yield {"event": "done", "data": {"content": full_text, "session_id": session_id}}
