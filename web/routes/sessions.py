"""会话管理路由。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from assistant.core import AgentMessage
from storage.repositories import SessionRepo, MessageRepo
from web.services.title_service import generate_title

router = APIRouter()


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------

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
    project_id: str | None = None


class SyncMessagesRequest(BaseModel):
    messages: List[MessageOut]
    turns: int


class GenerateTitleRequest(BaseModel):
    user_message: str
    assistant_message: str


class UpdateTitleRequest(BaseModel):
    title: str


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions(project_id: str | None = None):
    """返回会话列表，可按 project_id 过滤。"""
    rows = await SessionRepo.list_all(project_id=project_id)
    return [
        SessionSummary(
            id=r.id,
            title=r.title,
            turns=r.turns,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
            project_id=r.project_id,
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


@router.put("/session/{session_id}/messages")
async def sync_messages(session_id: str, request: SyncMessagesRequest):
    """替换会话的消息（用于前端编辑/删除后的同步）。"""
    agent_msgs = [
        AgentMessage(role=m.role, content=m.content) for m in request.messages
    ]
    await MessageRepo.sync_messages(session_id, agent_msgs, request.turns)
    return {"ok": True}


@router.post("/session/{session_id}/generate-title")
async def generate_session_title(session_id: str, request: GenerateTitleRequest):
    """根据第一轮问答，通过 LLM 生成简洁的标题。"""
    title = await generate_title(
        request.user_message,
        request.assistant_message,
    )
    if title:
        await SessionRepo.set_title(session_id, title)
    return {"title": title}


@router.patch("/session/{session_id}/title")
async def update_session_title(session_id: str, request: UpdateTitleRequest):
    """手动更新会话标题。"""
    await SessionRepo.set_title(session_id, request.title)
    return {"ok": True}
