"""API routes for the chat web interface.

Provides:
  - POST /api/chat          – non-streaming REST endpoint
  - WS   /api/ws/chat       – WebSocket streaming endpoint
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from assistant.core import AgentMessage, AgentRunState, AgentState
from assistant.loop import AgentLoop
from assistant.providers.langgraph_openai import build_provider

router = APIRouter()

_sessions: Dict[str, AgentState] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


def _get_or_create_session(session_id: str | None = None) -> tuple[str, AgentState]:
    if session_id and session_id in _sessions:
        return session_id, _sessions[session_id]
    sid = session_id or str(uuid.uuid4())
    state = AgentState()
    _sessions[sid] = state
    return sid, state


def _require_env() -> dict:
    """Return LLM config from environment."""
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
    kw = {"model": model, "api_key": api_key, "temperature": 0.7}
    if base_url:
        kw["base_url"] = base_url
    return ChatOpenAI(**kw)


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


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat.

    Protocol (JSON):
      Client -> Server: {"type":"message","content":"...","session_id":"...?"}
      Server -> Client: {"type":"session","session_id":"..."}
      Server -> Client: {"type":"chunk","content":"..."}
      Server -> Client: {"type":"done","content":"full response"}
      Server -> Client: {"type":"error","content":"..."}
    """
    cfg = _require_env()
    await websocket.accept()
    session_id: str | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "content": "Invalid JSON"}
                )
                continue

            msg_type = data.get("type")
            if msg_type != "message":
                await websocket.send_json(
                    {"type": "error", "content": f"Unknown type: {msg_type}"}
                )
                continue

            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            session_id = data.get("session_id") or session_id
            session_id, state = _get_or_create_session(session_id)

            await websocket.send_json(
                {"type": "session", "session_id": session_id}
            )

            state.append(AgentMessage(role="user", content=user_content))

            llm = _build_llm(cfg["api_key"], cfg["model"], cfg["base_url"])
            lc_msgs = _to_lc_messages(state.messages, cfg["system_message"])

            full_text_parts: list[str] = []
            async for chunk in llm.astream(lc_msgs):
                token = chunk.content or ""
                if token:
                    full_text_parts.append(token)
                    await websocket.send_json(
                        {"type": "chunk", "content": token}
                    )

            full_text = "".join(full_text_parts)
            state.append(AgentMessage(role="assistant", content=full_text))
            state.turns += 1
            _sessions[session_id] = state

            await websocket.send_json(
                {"type": "done", "content": full_text}
            )

    except WebSocketDisconnect:
        pass
