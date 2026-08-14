"""
Agent 模块对外提供的“统一 LLM 请求接口（协议）”。

本文件属于 agent 层的契约，不依赖任何具体模型 SDK。
后端（web/）负责实现具体 LLM 适配器，并注入给 agent 使用。
"""

from __future__ import annotations

from typing import AsyncIterable, Iterable, Protocol, Union

from .core import AgentMessage, AgentState


class ProviderProtocol(Protocol):
    """统一的消息生成协议。"""

    def __call__(self, state: AgentState) -> Union[Iterable[AgentMessage], AsyncIterable[AgentMessage]]:
        ...