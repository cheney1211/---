"""聊天持久化的 SQLAlchemy ORM 模型。"""

from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# ---------------------------------------------------------------------------
# 项目
# ---------------------------------------------------------------------------


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    root_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 项目磁盘路径
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[List["SessionRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 历史消息压缩摘要
    provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    turns: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Optional["ProjectRow"]] = relationship(back_populates="sessions")
    messages: Mapped[List["MessageRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )
    pending_calls: Mapped[List["PendingToolCallRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
        Index("ix_messages_session_sid_id", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))  # user|assistant|system|tool
    kind: Mapped[str] = mapped_column(
        String(32), default="user"
    )  # user|assistant|tool_request|tool_result|status
    content: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_chunk: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["SessionRow"] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# 待处理的工具调用（崩溃恢复表）
# ---------------------------------------------------------------------------


class PendingToolCallRow(Base):
    __tablename__ = "pending_tool_calls"
    __table_args__ = (
        Index("ix_pending_session_status", "session_id", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("messages.id", ondelete="CASCADE")
    )
    call_id: Mapped[str] = mapped_column(String(128))
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="queued"
    )  # queued|running|done|error|skipped
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, index=True
    )
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["SessionRow"] = relationship(back_populates="pending_calls")
