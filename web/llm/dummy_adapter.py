"""
Dummy adapter for quick local testing (no network / API key needed).
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from .base import LLMAdapter


class DummyAdapter(LLMAdapter):
    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> str:
        return "dummy reply"

    async def chat_stream_events(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        yield {"event": "status", "data": {"status": "thinking"}}

        text = "dummy streaming reply"
        for ch in text:
            yield {"event": "chunk", "data": {"content": ch}}

        yield {"event": "done", "data": {"content": text}}
