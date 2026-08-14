from __future__ import annotations

import inspect
from typing import AsyncIterable, Callable, Iterable, List

from .core import AgentMessage, AgentRunState, AgentState
from .interfaces import ProviderProtocol


# Callback type: called for every message yielded by the provider.
# Chunk messages (metadata["chunk"]=True) are display-only and NOT stored in state.
OnMessageCallback = Callable[[AgentMessage], None]


class AgentLoop:
    def __init__(
        self,
        provider: ProviderProtocol,
        *,
        max_turns: int = 16,
        system_message: str | None = None,
        stop_keywords: Iterable[str] | None = None,
        stop_after_assistant: bool = True,
    ) -> None:
        self.provider = provider
        self.max_turns = max_turns
        self.system_message = system_message
        self.stop_keywords = [keyword.lower() for keyword in (stop_keywords or ["quit", "exit", ":q"])]
        self.stop_after_assistant = stop_after_assistant

    def _is_stop_candidate(self, message: AgentMessage) -> bool:
        return message.content.strip().lower() in set(self.stop_keywords)

    def run(
        self,
        *,
        seed_messages: List[AgentMessage] | None = None,
        state: AgentState | None = None,
        continue_after_assistant: bool = False,
        on_message: OnMessageCallback | None = None,
    ) -> AgentState:
        state = state or AgentState()
        if seed_messages:
            state.extend_messages(seed_messages)

        should_stop_after_assistant = self.stop_after_assistant and not continue_after_assistant

        while state.status == AgentRunState.RUNNING:
            if state.turns >= self.max_turns:
                state.status = AgentRunState.FINISHED
                break

            state.turns += 1
            saw_assistant_message = False
            new_messages = self.provider(state)

            if inspect.isawaitable(new_messages) or hasattr(new_messages, "__aiter__"):
                raise TypeError(
                    "AgentLoop.run received an async provider. "
                    "Use the async runner path (e.g. app.create_background_task) "
                    "or keep run_in_executor around a sync adapter."
                )

            for new_message in new_messages:
                is_chunk = new_message.metadata.get("chunk", False)

                # Streaming chunks: notify display layer but do NOT persist.
                if is_chunk:
                    if on_message:
                        on_message(new_message)
                    continue

                # Final message: persist and notify.
                state.append(new_message)
                if on_message:
                    on_message(new_message)

                if new_message.role == "assistant":
                    saw_assistant_message = True
                if new_message.is_stop() or self._is_stop_candidate(new_message):
                    state.status = AgentRunState.FINISHED
                    break

            if state.status == AgentRunState.FINISHED:
                break
            if should_stop_after_assistant and saw_assistant_message:
                state.status = AgentRunState.FINISHED
                break

        return state

    async def arun(
        self,
        *,
        seed_messages: List[AgentMessage] | None = None,
        state: AgentState | None = None,
        continue_after_assistant: bool = False,
        on_message: OnMessageCallback | None = None,
    ) -> AgentState:
        state = state or AgentState()
        if seed_messages:
            state.extend_messages(seed_messages)

        should_stop_after_assistant = self.stop_after_assistant and not continue_after_assistant

        while state.status == AgentRunState.RUNNING:
            if state.turns >= self.max_turns:
                state.status = AgentRunState.FINISHED
                break

            state.turns += 1
            saw_assistant_message = False
            new_messages = self.provider(state)

            if inspect.isawaitable(new_messages):
                new_messages = await new_messages

            if hasattr(new_messages, "__aiter__"):
                async for new_message in new_messages:  # type: ignore[union-attr]
                    is_chunk = new_message.metadata.get("chunk", False)

                    if is_chunk:
                        if on_message:
                            on_message(new_message)
                        continue

                    state.append(new_message)
                    if on_message:
                        on_message(new_message)

                    if new_message.role == "assistant":
                        saw_assistant_message = True
                    if new_message.is_stop() or self._is_stop_candidate(new_message):
                        state.status = AgentRunState.FINISHED
                        break
            else:
                for new_message in new_messages:  # type: ignore[assignment]
                    is_chunk = new_message.metadata.get("chunk", False)

                    if is_chunk:
                        if on_message:
                            on_message(new_message)
                        continue

                    state.append(new_message)
                    if on_message:
                        on_message(new_message)

                    if new_message.role == "assistant":
                        saw_assistant_message = True
                    if new_message.is_stop() or self._is_stop_candidate(new_message):
                        state.status = AgentRunState.FINISHED
                        break

            if state.status == AgentRunState.FINISHED:
                break
            if should_stop_after_assistant and saw_assistant_message:
                state.status = AgentRunState.FINISHED
                break

        return state
