"""
Base data structures for the skills system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Skill:
    """A higher-level capability that groups tools and guidance."""

    name: str
    description: str
    tags: List[str] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)
    instruction: str | None = None
    version: str = "0.1.0"
    author: str = "assistant"
