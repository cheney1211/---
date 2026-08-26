"""Session management routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from assistant.core import AgentMessage
from storage.repositories import SessionRepo, MessageRepo

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
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


class SyncMessagesRequest(BaseModel):
    messages: List[MessageOut]
    turns: int


# ---------------------------------------------------------------------------
# Endpoints
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


@router.put("/session/{session_id}/messages")
async def sync_messages(session_id: str, request: SyncMessagesRequest):
    """Replace the messages for a session (used after frontend edits/deletions)."""
    agent_msgs = [
        AgentMessage(role=m.role, content=m.content) for m in request.messages
    ]
    await MessageRepo.sync_messages(session_id, agent_msgs, request.turns)
    return {"ok": True}
