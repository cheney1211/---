"""
Skill routing tool.

When the LLM decides a user request should be handled by a specific skill,
it calls this tool. The backend detects the tool call and performs a
second LLM call with the full skill instruction injected.
"""

from __future__ import annotations

import json
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register

# Sentinel prefix used by routes.py to detect skill routing.
SKILL_ROUTING_PREFIX = "[SKILL_ROUTING]"


class CallSkillInput(BaseModel):
    """Input schema for call_skill."""
    skill_name: str = Field(description="The name of the skill to activate, e.g. 'calculator' or 'weather'")


class CallSkillTool(Tool):
    name: str = "call_skill"
    description: str = (
        "Activate a skill to handle the user's request. "
        "Use this when the user's question matches one of your available skills."
    )
    args_schema: Type[BaseModel] = CallSkillInput

    def _run(self, skill_name: str) -> str:
        # Return a marker that routes.py will intercept.
        # The actual skill invocation happens in the routing layer.
        return f"{SKILL_ROUTING_PREFIX} {skill_name}"


register(CallSkillTool())
