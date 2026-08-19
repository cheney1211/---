"""
后端 LLM 适配层的抽象基类。

所有具体模型适配器（OpenAI、Deepseek、Ollama 等）都实现这个基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


class LLMAdapter(ABC):
    """Base adapter with shared message conversion logic."""

    @property
    def llm(self) -> BaseChatModel:
        """暴露底层 LangChain BaseChatModel 实例，供 LangGraph 使用。"""
        return self._llm

    def _to_lc_messages(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> List[BaseMessage]:
        """Convert agent message dicts to LangChain messages.

        Handles standard roles (system/user/assistant) as well as
        tool-calling roles (assistant with tool_calls, tool results).
        """
        lc: List[BaseMessage] = []
        if system_message:
            lc.append(SystemMessage(content=system_message))
        for item in messages:
            role = item.get("role", "user")
            content = item.get("content", "") or ""
            if role == "system":
                lc.append(SystemMessage(content=content))
            elif role == "assistant":
                tool_calls = item.get("tool_calls")
                if tool_calls:
                    lc.append(AIMessage(content=content, tool_calls=tool_calls))
                else:
                    lc.append(AIMessage(content=content))
            elif role == "tool":
                lc.append(ToolMessage(
                    content=content,
                    tool_call_id=item.get("tool_call_id", ""),
                ))
            else:
                lc.append(HumanMessage(content=content))
        return lc

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        ...

    @abstractmethod
    async def chat_stream_events(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        ...
