"""待处理工具调用的启动恢复逻辑。

在 FastAPI 应用启动时调用一次。
安全策略参见 DESIGN.md / 计划：
  - running  -> error  （不自动重试，以避免重复的副作用）
  - queued   -> error  （除非存在幂等键）
"""

from __future__ import annotations

import logging
from typing import List

from .models import PendingToolCallRow
from .repositories import PendingToolRepo

logger = logging.getLogger("storage.recovery")


async def recover_pending_tool_calls() -> List[PendingToolCallRow]:
    """扫描被中断或排队中的工具调用并将其标记为安全状态。

    返回已转换为 ``error`` 状态的条目列表，
    调用方可以记录日志或在界面中展示。
    """
    pendings = await PendingToolRepo.list_resumable()
    handled: List[PendingToolCallRow] = []

    for p in pendings:
        if p.status == "running":
            # 执行过程中崩溃 -> 标记为错误，需要手动重试
            await PendingToolRepo.mark_error(
                p.id,
                "执行被中断（进程崩溃）。请手动重试。",
            )
            logger.warning(
                "待处理的工具调用 #%d [%s] 在关闭时仍在运行 -> 已标记为错误",
                p.id,
                p.tool_name,
            )
            handled.append(p)

        elif p.status == "queued":
            if p.idempotency_key:
                # 可以安全地自动重试：保持为 queued 状态（已经排队，无需更改）
                logger.info(
                    "待处理的工具调用 #%d [%s] 存在幂等键，"
                    "保持为排队状态以自动重试",
                    p.id,
                    p.tool_name,
                )
            else:
                # 没有幂等保证 -> 标记为错误
                await PendingToolRepo.mark_error(
                    p.id,
                    "应用在执行前重启。"
                    "不存在幂等键，请手动重试。",
                )
                logger.warning(
                    "待处理的工具调用 #%d [%s] 已排队但不存在幂等键 "
                    "-> 已标记为错误",
                    p.id,
                    p.tool_name,
                )
                handled.append(p)

    return handled
