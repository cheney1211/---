"""
将后端 LLM 适配器包装成 Agent 层可直接使用的 Provider。

Provider 负责：
1. 将 AgentState 中的消息转换为 adapter 所需的 dict 列表；
2. 调用 adapter 的流式接口；
3. 返回 AgentMessage（含 chunk 和最终结果）；
4. 当 LLM 返回 tool_calls 时，自动执行工具并将结果追加到 state，
   然后再次调用 LLM，直到得到纯文本回复。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional
from typing import AsyncIterable

from assistant.core import AgentMessage, AgentState

from .base import LLMAdapter

# Type for the tool executor function: (tool_name, arguments) -> result_string
ToolExecutor = Callable[[str, Any], str]


class AssistantLLMProvider:
    """Wraps an LLMAdapter with tool-calling loop support.

    When *tools* and *tool_executor* are provided, the provider will:
    - Pass tool definitions to the LLM on every call.
    - If the LLM returns tool_calls, execute them via *tool_executor*,
      append tool results to *state*, and call the LLM again.
    - Repeat until the LLM returns a plain text response.
    """

    def __init__(
        self,
        adapter: LLMAdapter,
        *,
        system_message: str | None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[ToolExecutor] = None,
        max_tool_rounds: int = 5,
    ) -> None:
        self.adapter = adapter
        self.system_message = system_message
        self.tools = tools or []
        self.tool_executor = tool_executor
        self.max_tool_rounds = max_tool_rounds

    def _to_dict_messages(self, state: AgentState) -> List[Dict[str, Any]]:
        """Convert AgentState messages to dicts, preserving tool metadata."""
        result: List[Dict[str, Any]] = []
        for msg in state.messages:
            d: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.metadata.get("tool_calls"):
                d["tool_calls"] = msg.metadata["tool_calls"]
                d["content"] = msg.content or None
            if msg.metadata.get("tool_call_id"):
                d["tool_call_id"] = msg.metadata["tool_call_id"]
            result.append(d)
        return result

    async def __call__(self, state: AgentState) -> AsyncIterable[AgentMessage]:
        """Call the LLM, handling tool calls in a loop until a text response."""
        tool_round = 0
        while tool_round <= self.max_tool_rounds:
            dict_messages = self._to_dict_messages(state)
            tool_calls_seen = False
            tool_calls_to_execute: list = []

            async for event in self.adapter.chat_stream_events(
                dict_messages,
                system_message=self.system_message,
                tools=self.tools or None,
            ):
                event_type = event.get("event")
                event_data = event.get("data", {})

                if event_type == "chunk":
                    yield AgentMessage(
                        role="assistant",
                        content=event_data.get("content", ""),
                        metadata={"chunk": True},
                    )

                elif event_type == "tool_calls":
                    tool_calls_seen = True
                    tool_calls_to_execute = event_data.get("tool_calls", [])

                elif event_type == "done":
                    yield AgentMessage(
                        role="assistant",
                        content=event_data.get("content", ""),
                    )

            # If no tool calls, we're done
            if not tool_calls_seen:
                break

            tool_round += 1
            if tool_round > self.max_tool_rounds:
                # Safety limit reached — yield a warning and stop
                yield AgentMessage(
                    role="assistant",
                    content=f"[Warning] Tool calling limit ({self.max_tool_rounds} rounds) reached. Stopping.",
                )
                break

            # Append the assistant message with tool_calls to state
            state.append(AgentMessage(
                role="assistant",
                content="",
                metadata={"tool_calls": tool_calls_to_execute},
            ))

            # Execute each tool call and append results to state
            for tc in tool_calls_to_execute:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})
                tool_call_id = tc.get("id", "")

                if self.tool_executor:
                    try:
                        result = self.tool_executor(tool_name, tool_args)
                    except Exception as e:
                        result = f"Error: {e}"
                else:
                    result = f"Tool '{tool_name}' is not available"

                state.append(AgentMessage(
                    role="tool",
                    content=str(result),
                    metadata={"tool_call_id": tool_call_id},
                ))

            # Loop again — the LLM will see the tool results and respond


def build_agent_provider(
    adapter: LLMAdapter,
    *,
    system_message: str | None = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_executor: Optional[ToolExecutor] = None,
    max_tool_rounds: int = 5,
) -> AssistantLLMProvider:
    return AssistantLLMProvider(
        adapter=adapter,
        system_message=system_message,
        tools=tools,
        tool_executor=tool_executor,
        max_tool_rounds=max_tool_rounds,
    )
