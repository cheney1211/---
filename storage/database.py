"""SQLite 数据库引擎和会话工厂。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = _ROOT / "data" / "chat.db"


def _db_url() -> str:
    raw = os.getenv("CHAT_DB_PATH", str(DEFAULT_DB_PATH))
    p = Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{p.as_posix()}"


# ---------------------------------------------------------------------------
# 基类 / 引擎 / 会话
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()。")
    return _engine


async def init_db() -> None:
    """创建引擎、启用 WAL 模式，并在表不存在时创建所有表。"""
    global _engine, _session_factory
    if _engine is not None:
        return
    url = _db_url()
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    # 使用 WAL 模式以获得更好的并发性能
    async with _engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """提供事务性的异步会话上下文。"""
    if _session_factory is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()。")
    async with _session_factory() as session:
        async with session.begin():
            yield session
