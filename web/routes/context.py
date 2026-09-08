"""上下文管理路由 — Token 统计与压缩操作。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from assistant.context_manager import (
    get_context_usage,
    compress_context,
    count_system_tokens,
    get_model_context_window,
)
from assistant.core import AgentMessage
from storage.repositories import SessionRepo, MessageRepo
from web.llm import get_default_system_message

logger = logging.getLogger("context_routes")

router = APIRouter()


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class ContextStatsResponse(BaseModel):
    total_tokens: int
    max_tokens: int
    usage_percent: float
    message_count: int
    system_tokens: int
    messages_tokens: int


class CompressRequest(BaseModel):
    keep_recent_turns: int = 5
    context_window_size: int = 128000


class CompressResponse(BaseModel):
    before_tokens: int
    after_tokens: int
    freed_percent: float
    summary: str
    compressed_count: int
    kept_count: int


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/session/{session_id}/context-stats", response_model=ContextStatsResponse)
async def get_context_stats(session_id: str, context_window_size: int = 128000):
    """返回指定会话的上下文 Token 使用统计。"""
    messages = await MessageRepo.list_recent(session_id)
    system_message = get_default_system_message()

    stats = get_context_usage(messages, system_message, context_window_size=context_window_size)
    return ContextStatsResponse(
        total_tokens=stats.total_tokens,
        max_tokens=stats.max_tokens,
        usage_percent=stats.usage_percent,
        message_count=stats.message_count,
        system_tokens=stats.system_tokens,
        messages_tokens=stats.messages_tokens,
    )


@router.post("/session/{session_id}/compress", response_model=CompressResponse)
async def compress_session(session_id: str, body: CompressRequest = CompressRequest()):
    """手动触发指定会话的上下文压缩。"""
    # 加载消息
    messages = await MessageRepo.list_recent(session_id)
    system_message = get_default_system_message()

    if len(messages) < 4:
        return CompressResponse(
            before_tokens=0,
            after_tokens=0,
            freed_percent=0.0,
            summary="消息数量过少，无需压缩。",
            compressed_count=0,
            kept_count=len(messages),
        )

    # 获取已有的摘要
    existing_summary = await SessionRepo.get_summary(session_id)

    # 计算压缩前 token
    from assistant.context_manager import count_system_tokens, count_messages_tokens
    before_tokens = count_system_tokens(system_message) + count_messages_tokens(messages)

    # 构建压缩提示词
    from assistant.context_manager import (
        split_messages_for_compression,
        build_compression_messages,
    )
    to_compress, to_keep = split_messages_for_compression(messages, body.keep_recent_turns)

    if not to_compress:
        return CompressResponse(
            before_tokens=before_tokens,
            after_tokens=before_tokens,
            freed_percent=0.0,
            summary="保留窗口内的消息不压缩。",
            compressed_count=0,
            kept_count=len(messages),
        )

    prompt = build_compression_messages(to_compress, existing_summary)

    # 使用当前 LLM provider 生成摘要
    from web.llm import get_adapter, get_default_provider_name
    provider_name = get_default_provider_name()
    adapter = get_adapter(provider_name)

    try:
        summary = adapter.llm.invoke(prompt)
        summary_text = summary.content if hasattr(summary, "content") else str(summary)
    except Exception as e:
        logger.error("[compress] LLM 调用失败: %s", e)
        return CompressResponse(
            before_tokens=before_tokens,
            after_tokens=before_tokens,
            freed_percent=0.0,
            summary=f"压缩失败: {e}",
            compressed_count=0,
            kept_count=len(messages),
        )

    # 保存摘要到数据库
    if existing_summary:
        combined = f"{existing_summary}\n\n---\n\n{summary_text}"
    else:
        combined = summary_text
    await SessionRepo.set_summary(session_id, combined)

    # 计算压缩后 token
    from assistant.core import AgentMessage
    summary_msg = AgentMessage(role="system", content=f"## 历史对话摘要\n{summary_text}")
    new_messages = [summary_msg] + list(to_keep)
    after_tokens = count_system_tokens(system_message) + count_messages_tokens(new_messages)
    freed_percent = ((before_tokens - after_tokens) / before_tokens * 100) if before_tokens > 0 else 0.0

    return CompressResponse(
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        freed_percent=round(freed_percent, 2),
        summary=summary_text,
        compressed_count=len(to_compress),
        kept_count=len(to_keep),
    )
