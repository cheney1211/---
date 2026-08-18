"""
Ollama adapter.

Wraps langchain-ollama ChatOllama for local model inference.
Falls back to OpenAI-compatible mode if langchain_ollama is not installed.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessageChunk

from .base import LLMAdapter

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaAdapter(LLMAdapter):
    def __init__(
        self,
        *,
        model: str = "qwen2.5:7b",
        base_url: str | None = None,
        temperature: float = 0.7,
    ) -> None:
        self._model = model
        self._base_url = base_url or _DEFAULT_BASE_URL
        self._temperature = temperature

        # Try native langchain-ollama first; fall back to OpenAI-compatible mode.
        try:
            from langchain_ollama import ChatOllama

            self._llm = ChatOllama(
                model=model,
                base_url=self._base_url,
                temperature=temperature,
            )
            self._use_native = True
        except ImportError:
            from langchain_openai import ChatOpenAI

            self._llm = ChatOpenAI(
                model=model,
                base_url=f"{self._base_url}/v1",
                api_key="ollama",
                temperature=temperature,
                streaming=True,
            )
            self._use_native = False

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
