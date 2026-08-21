"""Repository layer: async DB helpers for sessions, messages, pending tool calls."""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core import AgentMessage
from .database import session_scope
from .models import MessageRow, PendingToolCallRow, SessionRow


# ---------------------------------------------------------------------------
# SessionRepo
# ---------------------------------------------------------------------------


class SessionRepo:
    """CRUD for chat sessions."""

    @staticmethod
    async def get_or_create(
        session_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> SessionRow:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row is None:
                row = SessionRow(id=session_id, provider=provider, model=model)
                s.add(row)
                await s.flush()
            return row

    @staticmethod
    async def touch(session_id: str) -> None:
        async with session_scope() as s:
            await s.execute(
                update(SessionRow)
                .where(SessionRow.id == session_id)
                .values(updated_at=_dt.datetime.now(_dt.timezone.utc))
            )

    @staticmethod
    async def delete(session_id: str) -> bool:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row is None:
                return False
            await s.delete(row)
            return True

    @staticmethod
    async def set_turns(session_id: str, turns: int) -> None:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row:
                row.turns = turns


# ---------------------------------------------------------------------------
# MessageRepo
# ---------------------------------------------------------------------------


class MessageRepo:
    """Read/write chat messages."""

    @staticmethod
    async def append(
        session_id: str,
        msg: AgentMessage,
        *,
        kind: str = "user",
        is_chunk: bool = False,
    ) -> MessageRow:
        """Write a single message to the DB.

        *kind* must be one of: user | assistant | tool_request | tool_result | status.
        """
        async with session_scope() as s:
            row = MessageRow(
                session_id=session_id,
                role=msg.role,
                kind=kind,
                content=msg.content,
                tool_calls=msg.metadata.get("tool_calls"),
                tool_call_id=msg.metadata.get("tool_call_id"),
                tool_name=msg.metadata.get("tool_name"),
                is_chunk=is_chunk,
            )
            s.add(row)
            await s.flush()
            return row

    @staticmethod
    async def list_recent(
        session_id: str, *, limit: int = 200
    ) -> List[AgentMessage]:
        """Load the most recent messages to rebuild an in-memory AgentState.

        Skips chunk-only rows and status rows.
        """
        async with session_scope() as s:
            stmt = (
                select(MessageRow)
                .where(
                    MessageRow.session_id == session_id,
                    MessageRow.is_chunk == False,  # noqa: E712
                    MessageRow.kind != "status",
                )
                .order_by(MessageRow.id.desc())
                .limit(limit)
            )
            result = await s.execute(stmt)
            rows = list(reversed(result.scalars().all()))

        messages: List[AgentMessage] = []
        for r in rows:
            meta: Dict[str, Any] = {}
            if r.tool_calls is not None:
                meta["tool_calls"] = r.tool_calls
            if r.tool_call_id is not None:
                meta["tool_call_id"] = r.tool_call_id
            if r.tool_name is not None:
                meta["tool_name"] = r.tool_name
            messages.append(
                AgentMessage(role=r.role, content=r.content or "", metadata=meta)
            )
        return messages

    @staticmethod
    async def get_turns(session_id: str) -> int:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            return row.turns if row else 0

    @staticmethod
    async def sync_messages(
        session_id: str, messages: List[AgentMessage], turns: int
    ) -> None:
        """Replace all messages for a session (frontend delete/edit sync)."""
        async with session_scope() as s:
            # Delete old
            old = await s.execute(
                select(MessageRow).where(MessageRow.session_id == session_id)
            )
            for row in old.scalars():
                await s.delete(row)

            # Insert new
            for i, msg in enumerate(messages):
                kind = msg.role if msg.role in ("user", "assistant", "system") else "user"
                s.add(
                    MessageRow(
                        session_id=session_id,
                        role=msg.role,
                        kind=kind,
                        content=msg.content,
                    )
                )

            # Update turns
            session_row = await s.get(SessionRow, session_id)
            if session_row:
                session_row.turns = turns


# ---------------------------------------------------------------------------
# PendingToolRepo
# ---------------------------------------------------------------------------


class PendingToolRepo:
    """Manage pending tool calls (crash recovery)."""

    @staticmethod
    async def create(
        session_id: str,
        message_id: int,
        call_id: str,
        tool_name: str,
        arguments: dict,
        *,
        idempotency_key: str | None = None,
    ) -> PendingToolCallRow:
        async with session_scope() as s:
            row = PendingToolCallRow(
                session_id=session_id,
                message_id=message_id,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                status="queued",
                idempotency_key=idempotency_key,
            )
            s.add(row)
            await s.flush()
            return row

    @staticmethod
    async def mark_running(pending_id: int) -> None:
        async with session_scope() as s:
            row = await s.get(PendingToolCallRow, pending_id)
            if row:
                row.status = "running"
                row.attempt_count += 1

    @staticmethod
    async def mark_done(pending_id: int) -> None:
        async with session_scope() as s:
            row = await s.get(PendingToolCallRow, pending_id)
            if row:
                row.status = "done"

    @staticmethod
    async def mark_error(pending_id: int, error: str) -> None:
        async with session_scope() as s:
            row = await s.get(PendingToolCallRow, pending_id)
            if row:
                row.status = "error"
                row.last_error = error

    @staticmethod
    async def list_resumable(session_id: str | None = None) -> List[PendingToolCallRow]:
        """Return pending calls that need recovery attention.

        Includes queued and running entries.
        """
        async with session_scope() as s:
            stmt = select(PendingToolCallRow).where(
                PendingToolCallRow.status.in_(["queued", "running"])
            )
            if session_id:
                stmt = stmt.where(PendingToolCallRow.session_id == session_id)
            result = await s.execute(stmt)
            return list(result.scalars().all())
