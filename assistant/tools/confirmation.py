"""人工确认管理器，用于工具执行审批的人机交互环节。

当一个设置了 requires_confirmation=True 的工具即将执行时，
系统会暂停并等待用户通过 confirmation_id 进行批准或拒绝。
此模块被 Web 端（SSE + POST）和 CLI 端（命令行提示）流程共同使用。

持久化层：
  ApprovalStore 将"始终允许"的指纹写入 SQLite 表 user_approval_fingerprints，
  与 LangGraph 的 checkpoint 表共库但独立，通过 WAL 模式 + 超时机制避免写冲突。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("confirmation")

# ======================================================================
# 高危操作黑名单
# ======================================================================

# 匹配规则：tool_name 精确匹配 + args_pattern 在参数字符串中子串匹配（不区分大小写）
HIGH_RISK_PATTERNS = [
    # ---- Linux/macOS ----
    {"tool": "bash", "args_pattern": "rm -rf"},
    {"tool": "bash", "args_pattern": "rm -fr"},
    {"tool": "bash", "args_pattern": "git push --force"},
    {"tool": "bash", "args_pattern": "git push -f"},
    {"tool": "bash", "args_pattern": "git reset --hard"},
    {"tool": "bash", "args_pattern": "git clean -fd"},
    {"tool": "bash", "args_pattern": "mkfs"},
    {"tool": "bash", "args_pattern": "dd if="},
    {"tool": "bash", "args_pattern": "chmod 777"},
    {"tool": "bash", "args_pattern": "> /dev/"},
    # ---- Windows cmd ----
    {"tool": "bash", "args_pattern": "rmdir /s"},
    {"tool": "bash", "args_pattern": "del /f"},
    {"tool": "bash", "args_pattern": "format "},
    {"tool": "bash", "args_pattern": "diskpart"},
    {"tool": "bash", "args_pattern": "reg delete"},
    {"tool": "bash", "args_pattern": "takeown"},
    # ---- PowerShell ----
    {"tool": "bash", "args_pattern": "remove-item"},
    {"tool": "bash", "args_pattern": "remove-item -recurse"},
]


# 指纹只取这些参数作为"操作标识"，忽略内容类参数
_IDENTITY_PARAM_KEYS = {
    "path", "file_path", "filePath",
    "dir", "directory", "folder", "root",
    "command", "cmd",
}


def generate_fingerprint(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """生成工具调用的指纹。

    指纹 = MD5(tool_name + 身份参数)
    只取路径/命令等标识性参数，忽略 content、old_str、new_str 等内容参数。
    例如 write_file + /a.txt 无论写入什么内容，指纹相同。
    """
    identity = {k: v for k, v in tool_args.items() if k in _IDENTITY_PARAM_KEYS}
    # 如果没有命中任何身份参数，退化为使用全部参数
    if not identity:
        identity = tool_args
    sorted_args = json.dumps(identity, sort_keys=True, ensure_ascii=False)
    raw = f"{tool_name}{sorted_args}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def is_high_risk(tool_name: str, tool_args: Dict[str, Any]) -> bool:
    """检查是否为高危操作。"""
    args_str = json.dumps(tool_args, sort_keys=True, ensure_ascii=False).lower()
    for pattern in HIGH_RISK_PATTERNS:
        if pattern["tool"] == tool_name:
            if pattern["args_pattern"].lower() in args_str:
                logger.warning("检测到高危操作: tool=%s, pattern=%s",
                               tool_name, pattern["args_pattern"])
                return True
    return False


def normalize_workspace_path(path: str) -> str:
    """归一化工作区路径，确保同一物理目录在不同写法下产生相同 key。

    - 转为绝对路径
    - 统一为正斜杠（Windows 上反斜杠 -> 正斜杠）
    - 去除末尾分隔符
    - Windows 盘符统一小写
    """
    if not path:
        return ""
    p = Path(path).resolve()
    s = str(p).replace("\\", "/")
    # Windows 盘符小写: C:/... -> c:/...
    if len(s) >= 2 and s[1] == ":":
        s = s[0].lower() + s[1:]
    return s.rstrip("/")


# ======================================================================
# 持久化指纹存储
# ======================================================================

# 表名避开 checkpoint_ 前缀，防止 LangGraph 升级时误伤
_TABLE = "user_approval_fingerprints"


class ApprovalStore:
    """SQLite 持久化存储"始终允许"的指纹。

    与 LangGraph 的 checkpointer 共用同一个 .db 文件，但操作独立的表。
    通过 WAL 模式 + busy timeout 最大化缓解并发写冲突。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def init(self) -> None:
        """建表 + 开启 WAL。应在应用启动时同步调用一次。"""
        self._conn = sqlite3.connect(self._db_path, timeout=10.0, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")  # 10 秒
        self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_root TEXT    NOT NULL,
                fingerprint   TEXT    NOT NULL,
                tool_name     TEXT    NOT NULL,
                created_at    INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(workspace_root, fingerprint)
            )
        """)
        self._conn.commit()
        logger.info("ApprovalStore 已初始化: %s", self._db_path)

    def close(self) -> None:
        """关闭连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # 读写操作（同步，调用方需注意在 async 上下文中快速返回）
    # ------------------------------------------------------------------

    def is_allowed(self, workspace_root: str, fingerprint: str) -> bool:
        """查询指定工作区下是否存在该指纹。"""
        ws = normalize_workspace_path(workspace_root)
        cur = self._conn.execute(
            f"SELECT 1 FROM {_TABLE} WHERE workspace_root=? AND fingerprint=?",
            (ws, fingerprint),
        )
        return cur.fetchone() is not None

    def add_approval(
        self,
        workspace_root: str,
        fingerprint: str,
        tool_name: str,
    ) -> None:
        """插入一条审批记录（已存在则忽略）。"""
        ws = normalize_workspace_path(workspace_root)
        try:
            self._conn.execute(
                f"INSERT OR IGNORE INTO {_TABLE}"
                f" (workspace_root, fingerprint, tool_name) VALUES (?, ?, ?)",
                (ws, fingerprint, tool_name),
            )
            self._conn.commit()
            logger.info("ApprovalStore: 已写入 fingerprint=%s tool=%s ws=%s",
                        fingerprint, tool_name, ws)
        except sqlite3.OperationalError as e:
            logger.error("ApprovalStore 写入失败: %s", e)

    def remove_approval(self, workspace_root: str, fingerprint: str) -> bool:
        """删除一条审批记录。返回是否确实删除了。"""
        ws = normalize_workspace_path(workspace_root)
        cur = self._conn.execute(
            f"DELETE FROM {_TABLE} WHERE workspace_root=? AND fingerprint=?",
            (ws, fingerprint),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self, workspace_root: Optional[str] = None) -> int:
        """清除审批记录。指定工作区则只清该区，否则全清。返回删除行数。"""
        if workspace_root:
            ws = normalize_workspace_path(workspace_root)
            cur = self._conn.execute(
                f"DELETE FROM {_TABLE} WHERE workspace_root=?", (ws,),
            )
        else:
            cur = self._conn.execute(f"DELETE FROM {_TABLE}")
        self._conn.commit()
        return cur.rowcount

    def list_approvals(self, workspace_root: Optional[str] = None) -> list[Dict[str, Any]]:
        """列出审批记录（调试/管理用）。"""
        if workspace_root:
            ws = normalize_workspace_path(workspace_root)
            cur = self._conn.execute(
                f"SELECT workspace_root, fingerprint, tool_name, created_at"
                f" FROM {_TABLE} WHERE workspace_root=? ORDER BY created_at DESC",
                (ws,),
            )
        else:
            cur = self._conn.execute(
                f"SELECT workspace_root, fingerprint, tool_name, created_at"
                f" FROM {_TABLE} ORDER BY created_at DESC",
            )
        return [
            {"workspace_root": r[0], "fingerprint": r[1],
             "tool_name": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]


# ======================================================================
# 确认请求
# ======================================================================

@dataclass
class ConfirmationRequest:
    """一个待处理的确认请求。"""
    confirmation_id: str
    tool_name: str
    tool_args: Dict[str, Any]
    description: str
    workspace_root: str = ""
    _future: asyncio.Future = field(
        default_factory=lambda: asyncio.get_event_loop().create_future()
    )


# ======================================================================
# 确认管理器
# ======================================================================

class ConfirmationManager:
    """管理待处理的确认请求。

    工作流程：
      1. create_request() -> 返回带有 confirmation_id 的 ConfirmationRequest
      2. 向前端（SSE）或命令行提示（CLI）发出 confirmation_required 事件
      3. await request._future（暂停执行）
      4. resolve() 由确认 API 端点或 CLI 输入调用
      5. 根据用户的决定恢复执行

    指纹管理：
      - 用户选择"始终允许"时，生成指纹并持久化到 SQLite
      - 后续相同操作（工具名+参数）自动跳过确认
      - 高危操作永远不允许"始终允许"
    """

    def __init__(self, store: Optional[ApprovalStore] = None) -> None:
        self._pending: Dict[str, ConfirmationRequest] = {}
        self._store = store

    def set_store(self, store: ApprovalStore) -> None:
        """设置持久化存储（用于延迟初始化）。"""
        self._store = store

    # ------------------------------------------------------------------
    # 请求生命周期
    # ------------------------------------------------------------------

    def create_request(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        description: str = "",
        workspace_root: str = "",
    ) -> ConfirmationRequest:
        """创建一个新的确认请求并将其注册。"""
        req = ConfirmationRequest(
            confirmation_id=str(uuid.uuid4()),
            tool_name=tool_name,
            tool_args=tool_args,
            description=description
                or f"工具 '{tool_name}' 需要确认授权。参数: {tool_args}",
            workspace_root=workspace_root,
        )
        self._pending[req.confirmation_id] = req
        logger.info(
            "已为工具 '%s' 创建确认请求 %s (workspace=%s)",
            tool_name, req.confirmation_id, workspace_root,
        )
        return req

    def resolve(
        self,
        confirmation_id: str,
        approved: bool,
        allow_always: bool = False,
        workspace_root: str = "",
    ) -> bool:
        """处理一个待处理的确认请求。

        Args:
            confirmation_id: 确认请求 ID
            approved: 是否批准
            allow_always: 是否允许后续相同操作不再询问
            workspace_root: 项目根目录（用于指纹隔离）
        """
        req = self._pending.pop(confirmation_id, None)
        if req is None:
            logger.warning("确认请求 %s 未找到", confirmation_id)
            return False
        if req._future.done():
            logger.warning("确认请求 %s 已经处理过了", confirmation_id)
            return False

        # 批准 + 始终允许 → 持久化指纹
        if approved and allow_always:
            if not is_high_risk(req.tool_name, req.tool_args):
                fp = generate_fingerprint(req.tool_name, req.tool_args)
                self._add_fingerprint(workspace_root, fp, req.tool_name)
                logger.info("已存储指纹: workspace=%s, fp=%s, tool=%s",
                            workspace_root, fp, req.tool_name)
            else:
                logger.warning("高危操作不允许'始终允许': tool=%s", req.tool_name)

        req._future.set_result(approved)
        logger.info("已处理确认请求 %s：%s (allow_always=%s)",
                     confirmation_id, "已批准" if approved else "已拒绝", allow_always)
        return True

    def get_request(self, confirmation_id: str) -> Optional[ConfirmationRequest]:
        """根据 ID 获取待处理的请求。"""
        return self._pending.get(confirmation_id)

    def list_pending(self) -> list[Dict[str, Any]]:
        """列出所有待处理的确认请求。"""
        return [
            {
                "confirmation_id": req.confirmation_id,
                "tool_name": req.tool_name,
                "tool_args": req.tool_args,
                "description": req.description,
                "workspace_root": req.workspace_root,
            }
            for req in self._pending.values()
        ]

    async def wait_for_decision(self, confirmation_id: str, timeout: float = 300.0) -> bool:
        """等待用户的决定。批准返回 True，拒绝返回 False。"""
        req = self._pending.get(confirmation_id)
        if req is None:
            raise ValueError(f"确认请求 {confirmation_id} 未找到")
        try:
            result = await asyncio.wait_for(req._future, timeout=timeout)
            return bool(result)
        except asyncio.TimeoutError:
            self._pending.pop(confirmation_id, None)
            raise TimeoutError(f"确认请求 {confirmation_id} 在 {timeout} 秒后超时")

    # ------------------------------------------------------------------
    # 指纹管理（委托给 ApprovalStore 持久化）
    # ------------------------------------------------------------------

    def _add_fingerprint(
        self, workspace_root: str, fingerprint: str, tool_name: str,
    ) -> None:
        """写入指纹到持久化存储。"""
        if self._store:
            self._store.add_approval(workspace_root, fingerprint, tool_name)

    def check_fingerprint_allowed(
        self,
        workspace_root: str,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> bool:
        """检查工具调用是否被允许（指纹匹配）。"""
        if is_high_risk(tool_name, tool_args):
            return False

        fingerprint = generate_fingerprint(tool_name, tool_args)

        if self._store:
            allowed = self._store.is_allowed(workspace_root, fingerprint)
            if allowed:
                logger.info("指纹匹配（持久化）: ws=%s, fp=%s, tool=%s",
                            workspace_root, fingerprint, tool_name)
            return allowed

        return False

    def remove_fingerprint(self, workspace_root: str, fingerprint: str) -> bool:
        """移除一个允许的指纹。"""
        if self._store:
            return self._store.remove_approval(workspace_root, fingerprint)
        return False

    def clear_fingerprints(self, workspace_root: Optional[str] = None) -> None:
        """清除所有指纹（可指定工作区）。"""
        if self._store:
            count = self._store.clear(workspace_root)
            logger.info("已清除 %d 条指纹记录 (workspace=%s)", count, workspace_root or "ALL")

    def list_fingerprints(self, workspace_root: Optional[str] = None) -> list[Dict[str, Any]]:
        """列出已存储的指纹（调试/管理用）。"""
        if self._store:
            return self._store.list_approvals(workspace_root)
        return []

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0
