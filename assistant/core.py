from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


@dataclass
class AgentMessage:
    role: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_stop(self) -> bool:
        stop_signal = self.metadata.get("stop", False)
        return self.role == "assistant" and bool(stop_signal)


class AgentRunState(str, Enum):
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class AgentState:
    messages: List[AgentMessage] = field(default_factory=list)
    status: AgentRunState = AgentRunState.RUNNING
    turns: int = 0

    def append(self, message: AgentMessage) -> None:
        self.messages.append(message)

    def extend_messages(self, messages: List[AgentMessage]) -> None:
        for message in messages:
            self.append(message)

    def last_user_message(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user":
                return message.content
        return ""
