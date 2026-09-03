"""仓库层：会话、消息、待处理工具调用的异步数据库辅助方法。"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from assistant.core import AgentMessage
from .database import session_scope
from .models import MessageRow, PendingToolCallRow, ProjectRow, SessionRow


# ---------------------------------------------------------------------------
# 项目仓库
# ---------------------------------------------------------------------------


class ProjectRepo:
    """项目的增删改查操作。"""

    @staticmethod
    async def create(project_id: str, name: str, root_path: str | None = None) -> ProjectRow:
        async with session_scope() as s:
            row = ProjectRow(id=project_id, name=name, root_path=root_path)
            s.add(row)
            await s.flush()
            return row

    @staticmethod
    async def get(project_id: str) -> ProjectRow | None:
        async with session_scope() as s:
            return await s.get(ProjectRow, project_id)

    @staticmethod
    async def list_all() -> list[ProjectRow]:
        async with session_scope() as s:
            stmt = select(ProjectRow).order_by(ProjectRow.created_at.asc())
            result = await s.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def rename(project_id: str, name: str) -> bool:
        async with session_scope() as s:
            row = await s.get(ProjectRow, project_id)
            if row is None:
                return False
            row.name = name
            return True

    @staticmethod
    async def set_root_path(project_id: str, root_path: str) -> bool:
        async with session_scope() as s:
            row = await s.get(ProjectRow, project_id)
            if row is None:
                return False
            row.root_path = root_path
            return True

    @staticmethod
    async def delete(project_id: str) -> bool:
        async with session_scope() as s:
            row = await s.get(ProjectRow, project_id)
            if row is None:
                return False
            await s.delete(row)
            return True

    @staticmethod
    async def is_empty() -> bool:
        async with session_scope() as s:
            result = await s.execute(select(ProjectRow).limit(1))
            return result.scalar() is None


# ---------------------------------------------------------------------------
# 会话仓库
# ---------------------------------------------------------------------------


class SessionRepo:
    """聊天会话的增删改查操作。"""

    @staticmethod
    async def get_or_create(
        session_id: str,
        *,
        project_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> SessionRow:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row is None:
                row = SessionRow(
                    id=session_id, project_id=project_id,
                    provider=provider, model=model,
                )
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
    async def list_all(project_id: str | None = None) -> List[SessionRow]:
        """返回按最近更新排序的会话列表，可选按项目筛选。"""
        async with session_scope() as s:
            stmt = select(SessionRow).order_by(SessionRow.updated_at.desc())
            if project_id is not None:
                stmt = stmt.where(SessionRow.project_id == project_id)
            result = await s.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def set_turns(session_id: str, turns: int) -> None:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row:
                row.turns = turns

    @staticmethod
    async def set_title(session_id: str, title: str) -> None:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row:
                row.title = title

    @staticmethod
    async def set_summary(session_id: str, summary: str) -> None:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            if row:
                row.summary = summary

    @staticmethod
    async def get_summary(session_id: str) -> str | None:
        async with session_scope() as s:
            row = await s.get(SessionRow, session_id)
            return row.summary if row else None


# ---------------------------------------------------------------------------
# 消息仓库
# ---------------------------------------------------------------------------


class MessageRepo:
    """聊天消息的读写操作。"""

    @staticmethod
    async def append(
        session_id: str,
        msg: AgentMessage,
        *,
        kind: str = "user",
        is_chunk: bool = False,
    ) -> MessageRow:
        """将单条消息写入数据库。

        *kind* 必须是以下之一：user | assistant | tool_request | tool_result | status。
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
        """加载最近的消息以重建内存中的 AgentState。

        跳过仅包含分片的行和状态行。
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
        """替换某个会话的所有消息（用于前端删除/编辑同步）。"""
        async with session_scope() as s:
            # 删除旧消息
            old = await s.execute(
                select(MessageRow).where(MessageRow.session_id == session_id)
            )
            for row in old.scalars():
                await s.delete(row)

            # 插入新消息
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

            # 更新轮次
            session_row = await s.get(SessionRow, session_id)
            if session_row:
                session_row.turns = turns


# ---------------------------------------------------------------------------
# 待处理工具调用仓库
# ---------------------------------------------------------------------------


class PendingToolRepo:
    """管理待处理的工具调用（崩溃恢复）。"""

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
        """返回需要恢复处理的待处理调用。

        包括排队中和运行中的条目。
        """
        async with session_scope() as s:
            stmt = select(PendingToolCallRow).where(
                PendingToolCallRow.status.in_(["queued", "running"])
            )
            if session_id:
                stmt = stmt.where(PendingToolCallRow.session_id == session_id)
            result = await s.execute(stmt)
            return list(result.scalars().all())
