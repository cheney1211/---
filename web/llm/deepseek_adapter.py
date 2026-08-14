"""
Deepseek adapter (OpenAI-compatible).

Uses langchain-openai ChatOpenAI with Deepseek's base URL.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .base import LLMAdapter

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


class DeepseekAdapter(LLMAdapter):
    def __init__(
        self,
        *,
        model: str = "deepseek-chat",
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.7,
    ) -> None:
        kwargs = {
            "model": model,
            "api_key": api_key,
            "base_url": base_url or _DEFAULT_BASE_URL,
            "temperature": temperature,
            "streaming": True,
        }
        self._llm = ChatOpenAI(**kwargs)

    def _to_lc_messages(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> List[BaseMessage]:
        lc: List[BaseMessage] = []
        if system_message:
            lc.append(SystemMessage(content=system_message))
        for item in messages:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role == "system":
                lc.append(SystemMessage(content=content))
            elif role == "assistant":
                lc.append(AIMessage(content=content))
            else:
                lc.append(HumanMessage(content=content))
        return lc

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> str:
        lc_messages = self._to_lc_messages(messages, system_message=system_message)
        result: BaseMessage = await self._llm.ainvoke(lc_messages)
        return result.content

    async def chat_stream_events(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        lc_messages = self._to_lc_messages(messages, system_message=system_message)

        yield {"event": "status", "data": {"status": "thinking"}}

        full_text_parts: List[str] = []
        async for event in self._llm.astream_events(lc_messages, version="v2"):
            kind = event.get("event")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if not chunk:
                    continue
                token = chunk.content or ""
                if token:
                    full_text_parts.append(token)
                    yield {"event": "chunk", "data": {"content": token}}

            elif kind == "on_tool_start":
                yield {
                    "event": "status",
                    "data": {"status": "tool_start", "name": event.get("name", "unknown")},
                }

            elif kind == "on_tool_end":
                yield {"event": "status", "data": {"status": "tool_end"}}

        full_text = "".join(full_text_parts)
        yield {"event": "done", "data": {"content": full_text}}
