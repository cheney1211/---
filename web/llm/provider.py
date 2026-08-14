"""
将后端 LLM 适配器包装成 Agent 层可直接使用的 Provider。

这里的 provider 只负责：
1. 将 AgentState 中的消息转换为 adapter 所需的 dict 列表；
2. 调用 adapter 的流式接口；
3. 返回 AgentMessage（含 chunk 和最终结果）。
"""

from __future__ import annotations

from typing import AsyncIterable, Dict, List

from assistant.core import AgentMessage, AgentState

from .base import LLMAdapter


class AssistantLLMProvider:
    def __init__(self, adapter: LLMAdapter, system_message: str | None = None) -> None:
        self.adapter = adapter
        self.system_message = system_message

    def _to_dict_messages(self, state: AgentState) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        for msg in state.messages:
            result.append({"role": msg.role, "content": msg.content})
        return result

    async def __call__(self, state: AgentState) -> AsyncIterable[AgentMessage]:
        dict_messages = self._to_dict_messages(state)

        async for event in self.adapter.chat_stream_events(
            dict_messages, system_message=self.system_message
        ):
            event_type = event.get("event")
            event_data = event.get("data", {})

            if event_type == "chunk":
                yield AgentMessage(
                    role="assistant",
                    content=event_data.get("content", ""),
                    metadata={"chunk": True},
                )

            elif event_type == "done":
                yield AgentMessage(
                    role="assistant",
                    content=event_data.get("content", ""),
                )


def build_agent_provider(
    adapter: LLMAdapter,
    *,
    system_message: str | None = None,
) -> AssistantLLMProvider:
    return AssistantLLMProvider(adapter=adapter, system_message=system_message)
