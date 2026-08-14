"""
Ollama adapter.

Wraps langchain-ollama ChatOllama for local model inference.
Falls back to OpenAI-compatible mode if langchain_ollama is not installed.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

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

    def _to_lc_messages(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> list:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        lc = []
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
        result = await self._llm.ainvoke(lc_messages)
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
