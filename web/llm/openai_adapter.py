"""
OpenAI-compatible adapter implementation.

This adapter wraps langchain-openai ChatOpenAI and translates agent
message dicts to LangChain messages.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessageChunk
from langchain_openai import ChatOpenAI

from .base import LLMAdapter


class OpenAIAdapter(LLMAdapter):
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.7,
    ) -> None:
        kwargs = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
            "streaming": True,
        }
        if base_url:
            kwargs["base_url"] = base_url

        self._llm = ChatOpenAI(**kwargs)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        lc_messages = self._to_lc_messages(messages, system_message=system_message)
        llm = self._llm.bind_tools(tools) if tools else self._llm
        result = await llm.ainvoke(lc_messages)
        return result.content or ""

    async def chat_stream_events(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        lc_messages = self._to_lc_messages(messages, system_message=system_message)
        llm = self._llm.bind_tools(tools) if tools else self._llm

        yield {"event": "status", "data": {"status": "thinking"}}

        full_text_parts: List[str] = []
        accumulated: AIMessageChunk | None = None

        async for chunk in llm.astream(lc_messages):
            if accumulated is None:
                accumulated = chunk
            else:
                accumulated = accumulated + chunk  # type: ignore[assignment]
            token = chunk.content or ""
            if token:
                full_text_parts.append(token)
                yield {"event": "chunk", "data": {"content": token}}

        full_text = "".join(full_text_parts)

        # Check if the LLM returned tool calls
        if accumulated and hasattr(accumulated, "tool_calls") and accumulated.tool_calls:
            yield {
                "event": "tool_calls",
                "data": {
                    "tool_calls": accumulated.tool_calls,
                    "content": full_text,
                },
            }
        else:
            yield {"event": "done", "data": {"content": full_text}}
