"""上下文管理器 — Token 计数与自动压缩引擎。

职责：
1. 精确计算消息列表的 Token 使用量
2. 判断当前上下文是否达到压缩阈值
3. 执行"滑动窗口 + 智能摘要"压缩策略
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import tiktoken

from assistant.core import AgentMessage, AgentState

logger = logging.getLogger("context_manager")

# 使用 cl100k_base 编码（GPT-4 / GPT-3.5-turbo / 大多数现代模型通用）
_ENCODING_NAME = "cl100k_base"

# 默认上下文窗口大小（用户未指定时使用）
DEFAULT_CONTEXT_WINDOW = 128_000

# 预留给系统提示词 + 模型响应的 Token 数
RESERVED_TOKENS = 4_096

# 压缩提示词文件路径
_COMPRESSION_PROMPT_PATH = Path(__file__).parent / "prompts" / "compression_prompt.md"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ContextStats:
    """上下文使用统计。"""
    total_tokens: int          # 当前消息总 Token 数
    max_tokens: int            # 模型最大上下文窗口
    usage_percent: float       # 使用率百分比 (0-100)
    message_count: int         # 消息条数
    system_tokens: int = 0     # 系统提示词 Token 数
    messages_tokens: int = 0   # 对话消息 Token 数


@dataclass
class CompressionResult:
    """压缩执行结果。"""
    before_tokens: int         # 压缩前 Token 数
    after_tokens: int          # 压缩后 Token 数
    freed_percent: float       # 释放百分比 (0-100)
    summary: str               # 生成的摘要内容
    compressed_count: int      # 被压缩的消息条数
    kept_count: int            # 保留的消息条数


# ---------------------------------------------------------------------------
# Token 计数
# ---------------------------------------------------------------------------

_encoder_cache: dict[str, tiktoken.Encoding] = {}


def _get_encoder() -> tiktoken.Encoding:
    """获取缓存的 tokenizer 编码器。"""
    if _ENCODING_NAME not in _encoder_cache:
        _encoder_cache[_ENCODING_NAME] = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoder_cache[_ENCODING_NAME]


def count_tokens(text: str) -> int:
    """计算单段文本的 Token 数。"""
    if not text:
        return 0
    encoder = _get_encoder()
    return len(encoder.encode(text))


def count_messages_tokens(messages: List[AgentMessage]) -> int:
    """计算消息列表的总 Token 数。

    每条消息有固定的格式开销（约 4 tokens），加上角色名和内容。
    """
    if not messages:
        return 0
    encoder = _get_encoder()
    total = 0
    for msg in messages:
        # 每条消息的格式开销: <|start|>{role}\n{content}<|end|>\n ≈ 4 tokens
        total += 4
        total += len(encoder.encode(msg.role))
        total += len(encoder.encode(msg.content or ""))
        # tool_calls 等 metadata 也需要计算
        tool_calls = msg.metadata.get("tool_calls")
        if tool_calls:
            import json
            total += len(encoder.encode(json.dumps(tool_calls, ensure_ascii=False)))
    return total


def count_system_tokens(system_message: str) -> int:
    """计算系统提示词的 Token 数（含格式开销）。"""
    if not system_message:
        return 0
    return count_tokens(system_message) + 4  # 格式开销


# ---------------------------------------------------------------------------
# 上下文窗口查询
# ---------------------------------------------------------------------------


def get_model_context_window() -> int:
    """获取模型的上下文窗口大小（返回默认值）。"""
    return DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# 上下文使用统计
# ---------------------------------------------------------------------------


def get_context_usage(
    messages: List[AgentMessage],
    system_message: str = "",
    *,
    provider: str | None = None,
    model: str | None = None,
    context_window_size: int = 0,
) -> ContextStats:
    """计算当前上下文的使用统计。

    Args:
        context_window_size: 手动指定的上下文窗口大小。0 表示自动检测。
    """
    system_tokens = count_system_tokens(system_message)
    messages_tokens = count_messages_tokens(messages)
    total = system_tokens + messages_tokens
    max_tokens = (
        context_window_size
        if context_window_size > 0
        else get_model_context_window()
    )

    # 可用空间 = 最大窗口 - 预留空间
    available = max_tokens - RESERVED_TOKENS
    usage_percent = (total / available * 100) if available > 0 else 100.0

    return ContextStats(
        total_tokens=total,
        max_tokens=max_tokens,
        usage_percent=round(usage_percent, 2),
        message_count=len(messages),
        system_tokens=system_tokens,
        messages_tokens=messages_tokens,
    )


def should_compress(
    messages: List[AgentMessage],
    system_message: str = "",
    *,
    threshold: float = 80.0,
    provider: str | None = None,
    model: str | None = None,
    context_window_size: int = 0,
    min_messages: int = 10,
) -> bool:
    """判断是否需要触发压缩。

    Args:
        messages: 当前消息列表
        system_message: 系统提示词
        threshold: 压缩阈值百分比 (0-100)
        provider: LLM 提供商名称
        model: 模型名称
        context_window_size: 手动指定的上下文窗口大小，0 表示自动检测
        min_messages: 最少消息数（低于此数不压缩，避免过度压缩）
    """
    if len(messages) < min_messages:
        return False

    stats = get_context_usage(
        messages, system_message,
        provider=provider, model=model,
        context_window_size=context_window_size,
    )
    return stats.usage_percent >= threshold


# ---------------------------------------------------------------------------
# 压缩引擎
# ---------------------------------------------------------------------------


def _load_compression_prompt() -> str:
    """加载压缩提示词模板。"""
    try:
        return _COMPRESSION_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("压缩提示词文件不存在: %s，使用默认提示词", _COMPRESSION_PROMPT_PATH)
        return (
            "请将以下对话历史压缩为一份高度精炼的结构化摘要。\n"
            "摘要需要包含：\n"
            "1. 【项目目标与约束】用户的核心需求和限制条件\n"
            "2. 【关键决策】已做出的重要技术决策和选择\n"
            "3. 【代码架构】涉及的文件、模块、函数等技术细节\n"
            "4. 【遗留问题】尚未解决的问题和待办事项\n"
            "5. 【当前进度】正在进行的工作和下一步计划\n\n"
            "对话历史：\n{history}\n\n"
            "请用中文输出摘要，保持简洁但不遗漏关键信息。"
        )


def _format_messages_for_compression(messages: List[AgentMessage]) -> str:
    """将消息列表格式化为可读文本，用于压缩提示词。"""
    lines = []
    for msg in messages:
        role_label = {"user": "用户", "assistant": "助手", "system": "系统", "tool": "工具"}.get(msg.role, msg.role)
        content = msg.content or ""
        # 截断过长的单条消息（避免超出 LLM 上下文）
        if len(content) > 2000:
            content = content[:2000] + "...(已截断)"
        lines.append(f"[{role_label}]: {content}")
    return "\n".join(lines)


def build_compression_messages(
    messages_to_compress: List[AgentMessage],
    existing_summary: str | None = None,
) -> str:
    """构建压缩请求的完整提示词。"""
    template = _load_compression_prompt()
    history_text = _format_messages_for_compression(messages_to_compress)

    if existing_summary:
        history_text = f"## 之前的摘要\n{existing_summary}\n\n## 新增对话\n{history_text}"

    return template.replace("{history}", history_text)


def split_messages_for_compression(
    messages: List[AgentMessage],
    keep_recent_turns: int = 5,
) -> tuple[List[AgentMessage], List[AgentMessage]]:
    """将消息分为"待压缩历史"和"保留近期"两部分。

    Args:
        messages: 完整消息列表
        keep_recent_turns: 保留最近的轮数（每轮 = 1条用户 + 1条助手）

    Returns:
        (to_compress, to_keep) — 待压缩的消息和保留的消息
    """
    if not messages:
        return [], []

    keep_count = keep_recent_turns * 2  # 每轮 2 条消息

    if len(messages) <= keep_count:
        # 消息数少于保留数，不压缩
        return [], messages

    to_keep = messages[-keep_count:]
    to_compress = messages[:-keep_count]
    return to_compress, to_keep


async def compress_context(
    session_id: str,
    state: AgentState,
    system_message: str,
    llm_caller,  # async callable: (messages: str) -> str
    *,
    keep_recent_turns: int = 5,
    existing_summary: str | None = None,
) -> CompressionResult:
    """执行上下文压缩。

    Args:
        session_id: 会话 ID
        state: 当前 AgentState（会被原地修改）
        system_message: 系统提示词（用于计算 token）
        llm_caller: 异步 LLM 调用函数，接收提示词返回摘要文本
        keep_recent_turns: 保留最近的轮数
        existing_summary: 已有的摘要（增量压缩时使用）

    Returns:
        CompressionResult 压缩结果
    """
    before_tokens = count_system_tokens(system_message) + count_messages_tokens(state.messages)

    to_compress, to_keep = split_messages_for_compression(state.messages, keep_recent_turns)

    if not to_compress:
        logger.info("[compress] 会话 %s 无需压缩（消息数不足）", session_id)
        return CompressionResult(
            before_tokens=before_tokens,
            after_tokens=before_tokens,
            freed_percent=0.0,
            summary="",
            compressed_count=0,
            kept_count=len(state.messages),
        )

    logger.info(
        "[compress] 会话 %s 开始压缩: %d 条待压缩, %d 条保留",
        session_id, len(to_compress), len(to_keep),
    )

    # 构建压缩提示词
    prompt = build_compression_messages(to_compress, existing_summary)

    # 调用 LLM 生成摘要
    try:
        summary = await llm_caller(prompt)
    except Exception as e:
        logger.error("[compress] 会话 %s 压缩失败: %s", session_id, e)
        # 压缩失败时不修改 state，返回原样
        return CompressionResult(
            before_tokens=before_tokens,
            after_tokens=before_tokens,
            freed_percent=0.0,
            summary="",
            compressed_count=0,
            kept_count=len(state.messages),
        )

    # 构建新的消息列表：[系统摘要消息] + [保留的近期消息]
    summary_msg = AgentMessage(
        role="system",
        content=f"## 历史对话摘要\n{summary}",
    )
    new_messages = [summary_msg] + list(to_keep)

    # 更新 state
    state.messages = new_messages

    after_tokens = count_system_tokens(system_message) + count_messages_tokens(new_messages)
    freed_percent = ((before_tokens - after_tokens) / before_tokens * 100) if before_tokens > 0 else 0.0

    logger.info(
        "[compress] 会话 %s 压缩完成: %d -> %d tokens (释放 %.1f%%)",
        session_id, before_tokens, after_tokens, freed_percent,
    )

    return CompressionResult(
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        freed_percent=round(freed_percent, 2),
        summary=summary,
        compressed_count=len(to_compress),
        kept_count=len(to_keep),
    )
