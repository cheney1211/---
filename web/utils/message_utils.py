"""共享的消息分类辅助工具。"""

from __future__ import annotations

from assistant.core import AgentMessage


def classify_and_extract(msg: AgentMessage) -> tuple[str, bool]:
    """返回给定 AgentMessage 的 (kind, is_chunk)。"""
    if msg.metadata.get("chunk"):
        return "status", True
    if msg.role == "tool":
        return "tool_result", False
    if msg.metadata.get("tool_calls"):
        return "tool_request", False
    return msg.role if msg.role in ("user", "assistant", "system") else "user", False
