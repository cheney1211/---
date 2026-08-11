"""Core AgentRunner: business logic for driving the agent loop.

UI-specific code (CLI, web) lives in separate modules.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import List

from .core import AgentMessage, AgentState, AgentRunState
from .loop import AgentLoop, OnMessageCallback, MessageProvider


@dataclass
class AgentRunnerConfig:
    name: str = "assistant"
    agent_name: str = "coco"
    user_name: str = "YOU"
    system_message: str | None = "You are a helpful assistant."
    max_turns: int = 16
    stop_keywords: List[str] | None = None
    stream: bool = False


class AgentRunner:
    def __init__(self, provider, config=None):
        self.provider = provider
        self.config = config or AgentRunnerConfig()
        self._loop = AgentLoop(
            self.provider,
            max_turns=self.config.max_turns,
            system_message=self.config.system_message,
            stop_keywords=self.config.stop_keywords,
        )
        self._state = AgentState()

    def create_state(self, user_message=None, on_message=None):
        seed_messages = []
        if user_message:
            seed_messages.append(AgentMessage(role="user", content=user_message))
        return self._loop.run(seed_messages=seed_messages, on_message=on_message)

    def continue_state(self, state, user_message, on_message=None):
        state.append(AgentMessage(role="user", content=user_message))
        state.status = AgentRunState.RUNNING
        return self._loop.run(state=state, continue_after_assistant=False, on_message=on_message)

    @staticmethod
    def _last_assistant_message(state):
        for message in reversed(state.messages):
            if message.role == "assistant":
                return message.content
        return None

    def _is_async_provider(self) -> bool:
        provider = self.provider
        try:
            sample = provider(self._state)
        except Exception:
            # Conservative: assume sync when provider cannot be sampled.
            return False
        return inspect.isawaitable(sample) or hasattr(sample, "__aiter__")

    async def acreate_state(self, user_message=None, on_message=None):
        seed_messages = []
        if user_message:
            seed_messages.append(AgentMessage(role="user", content=user_message))
        return await self._loop.arun(seed_messages=seed_messages, on_message=on_message)

    async def acontinue_state(self, state, user_message, on_message=None):
        state.append(AgentMessage(role="user", content=user_message))
        state.status = AgentRunState.RUNNING
        return await self._loop.arun(state=state, continue_after_assistant=False, on_message=on_message)
