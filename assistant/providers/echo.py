from __future__ import annotations

from typing import Iterable

from assistant.core import AgentMessage, AgentState
from assistant.loop import MessageProvider


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def build_provider() -> MessageProvider:
    def provider(state: AgentState) -> Iterable[AgentMessage]:
        user_text = state.last_user_message().strip()
        if not user_text:
            reply = "请发送一条消息，我会原样回复。"
        elif user_text.lower() in {"help", "帮助"}:
            reply = "我是一个回显示例 Agent。输入任意文本，我会把内容复述回去。"
        else:
            reply = f"你说的是：{_normalize_whitespace(user_text)}"
        yield AgentMessage(role="assistant", content=reply)

    return provider
