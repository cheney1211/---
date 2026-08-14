"""
后端 LLM 适配层的抽象基类。

所有具体模型适配器（OpenAI、Deepseek、Ollama 等）都实现这个基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List


class LLMAdapter(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def chat_stream_events(
        self,
        messages: List[Dict[str, str]],
        *,
        system_message: str | None = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        ...
