"""Shared message classification helpers."""

from __future__ import annotations

from assistant.core import AgentMessage


def classify_and_extract(msg: AgentMessage) -> tuple[str, bool]:
    """Return (kind, is_chunk) for a given AgentMessage."""
    if msg.metadata.get("chunk"):
        return "status", True
    if msg.role == "tool":
        return "tool_result", False
    if msg.metadata.get("tool_calls"):
        return "tool_request", False
    return msg.role if msg.role in ("user", "assistant", "system") else "user", False
