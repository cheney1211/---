"""人工确认管理器，用于工具执行审批的人机交互环节。

当一个设置了 requires_confirmation=True 的工具即将执行时，
系统会暂停并等待用户通过 confirmation_id 进行批准或拒绝。
此模块被 Web 端（SSE + POST）和 CLI 端（命令行提示）流程共同使用。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("confirmation")


@dataclass
class ConfirmationRequest:
    """一个待处理的确认请求。"""
    confirmation_id: str
    tool_name: str
    tool_args: Dict[str, Any]
    description: str
    _future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class ConfirmationManager:
    """管理待处理的确认请求。

    工作流程：
      1. create_request() -> 返回带有 confirmation_id 的 ConfirmationRequest
      2. 向前端（SSE）或命令行提示（CLI）发出 confirmation_required 事件
      3. await request._future（暂停执行）
      4. resolve() 由确认 API 端点或 CLI 输入调用
      5. 根据用户的决定恢复执行
    """

    def __init__(self) -> None:
        self._pending: Dict[str, ConfirmationRequest] = {}

    def create_request(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        description: str = "",
    ) -> ConfirmationRequest:
        """创建一个新的确认请求并将其注册。"""
        req = ConfirmationRequest(
            confirmation_id=str(uuid.uuid4()),
            tool_name=tool_name,
            tool_args=tool_args,
            description=description
                or f"工具 '{tool_name}' 需要确认授权。参数: {tool_args}",
        )
        self._pending[req.confirmation_id] = req
        logger.info(
            "已为工具 '%s' 创建确认请求 %s",
            tool_name,
            req.confirmation_id,
        )
        return req

    def resolve(self, confirmation_id: str, approved: bool) -> bool:
        """处理一个待处理的确认请求。

        如果请求被找到并已处理则返回 True，否则返回 False。
        """
        req = self._pending.pop(confirmation_id, None)
        if req is None:
            logger.warning("确认请求 %s 未找到", confirmation_id)
            return False
        if req._future.done():
            logger.warning("确认请求 %s 已经处理过了", confirmation_id)
            return False
        req._future.set_result(approved)
        logger.info(
            "已处理确认请求 %s：%s",
            confirmation_id,
            "已批准" if approved else "已拒绝",
        )
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
            }
            for req in self._pending.values()
        ]

    async def wait_for_decision(self, confirmation_id: str, timeout: float = 300.0) -> bool:
        """等待用户的决定。批准返回 True，拒绝返回 False。

        如果在超时时间内未收到响应则抛出 TimeoutError。
        """
        req = self._pending.get(confirmation_id)
        if req is None:
            raise ValueError(f"确认请求 {confirmation_id} 未找到")
        try:
            result = await asyncio.wait_for(req._future, timeout=timeout)
            return bool(result)
        except asyncio.TimeoutError:
            self._pending.pop(confirmation_id, None)
            raise TimeoutError(
                f"确认请求 {confirmation_id} 在 {timeout} 秒后超时"
            )

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0
