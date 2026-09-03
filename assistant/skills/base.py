"""
技能系统的基础数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Skill:
    """一种更高级别的能力，用于组合工具和指导信息。"""

    name: str
    description: str
    tags: List[str] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)
    instruction: str | None = None
    version: str = "0.1.0"
    author: str = "assistant"
