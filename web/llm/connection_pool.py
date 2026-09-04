"""
aiosqlite 连接池实现。

特性：
- WAL 模式开启，提升并发读写性能
- 连接健康检查（SELECT 1 验活）
- 自动归还连接到池
- 坏连接自动丢弃并重建
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import aiosqlite

logger = logging.getLogger("connection_pool")


class ConnectionPool:
    """简单的 aiosqlite 连接池。"""

    def __init__(self, db_path: str, min_size: int = 2, max_size: int = 10):
        self._db_path = db_path
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._lock = asyncio.Lock()
        self._closed = False

    async def _create_connection(self) -> aiosqlite.Connection:
        """创建新的数据库连接，开启 WAL 模式。"""
        conn = await aiosqlite.connect(self._db_path)
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        logger.debug("创建新连接，当前池大小: %d", self._size)
        return conn

    async def _check_connection(self, conn: aiosqlite.Connection) -> bool:
        """检查连接是否健康。"""
        try:
            await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """从池中获取连接，使用后自动归还。"""
        if self._closed:
            raise RuntimeError("连接池已关闭")

        conn = None
        created_new = False

        try:
            # 尝试从池中获取现有连接
            try:
                conn = self._pool.get_nowait()
                # 检查连接是否健康
                if not await self._check_connection(conn):
                    logger.warning("检测到坏连接，丢弃并创建新连接")
                    async with self._lock:
                        self._size -= 1
                    conn = await self._create_connection()
                    async with self._lock:
                        self._size += 1
                    created_new = True
            except asyncio.QueueEmpty:
                # 池为空，检查是否可以创建新连接
                async with self._lock:
                    if self._size < self._max_size:
                        conn = await self._create_connection()
                        self._size += 1
                        created_new = True

                if conn is None:
                    # 等待其他连接归还
                    logger.debug("连接池已满，等待连接归还...")
                    conn = await self._pool.get()

            yield conn

        finally:
            # 归还连接到池
            if conn is not None and not self._closed:
                try:
                    self._pool.put_nowait(conn)
                except asyncio.QueueFull:
                    # 池已满，关闭多余连接
                    await conn.close()
                    async with self._lock:
                        self._size -= 1

    async def close_all(self) -> None:
        """关闭所有连接。"""
        self._closed = True
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await conn.close()
            except asyncio.QueueEmpty:
                break
        self._size = 0
        logger.info("连接池已关闭")

    @property
    def size(self) -> int:
        """当前池大小。"""
        return self._size

    @property
    def available(self) -> int:
        """可用连接数。"""
        return self._pool.qsize()
