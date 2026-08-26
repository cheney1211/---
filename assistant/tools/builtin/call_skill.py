"""Skill routing tool.

When the LLM decides a user request should be handled by a specific skill,
it calls this tool. The tool internally invokes the LLM with the full
skill instruction injected, and returns the result as a normal tool response.
No second LLM call in routes.py -- everything happens in one graph loop.
"""

from __future__ import annotations

from typing import Optional, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..base import Tool

# Module-level references, configured by the provider at startup.
_llm: Optional[BaseChatModel] = None
_base_system_message: str = ""


def configure(llm: BaseChatModel, base_system_message: str) -> None:
    """Called once at startup to inject LLM and system message."""
    global _llm, _base_system_message
    _llm = llm
    _base_system_message = base_system_message


class CallSkillInput(BaseModel):
    """Input schema for call_skill."""
    skill_name: str = Field(description="The name of the skill to activate.")
    question: str = Field(
        default="",
        description="The user's original question to pass to the skill.",
    )


class CallSkillTool(Tool):
    name: str = "call_skill"
    description: str = (
        "Activate a skill to handle the user's request. "
        "Use this when the user's question matches one of your available skills. "
        "Pass the user's original question in the 'question' field."
    )
    args_schema: Type[BaseModel] = CallSkillInput

    def _run(self, skill_name: str, question: str = "") -> str:
        from assistant.skills import get_skill

        try:
            skill = get_skill(skill_name)
        except ValueError:
            return f"Error: skill '{skill_name}' not found."

        if _llm is None:
            return f"Error: LLM not configured for call_skill tool."

        # Build system message: base + full skill instruction
        parts = [_base_system_message]
        if skill.instruction:
            parts.append(skill.instruction)
        else:
            parts.append(f"You are now operating as the {skill.name} skill: {skill.description}")
        system_message = "\n\n".join(parts)

        # Invoke LLM with skill context
        messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=question or skill_name),
        ]
        try:
            response = _llm.invoke(messages)
            return response.content or "(empty response)"
        except Exception as e:
            return f"Error invoking skill '{skill_name}': {e}"

    async def _arun(self, skill_name: str, question: str = "") -> str:
        from assistant.skills import get_skill

        try:
            skill = get_skill(skill_name)
        except ValueError:
            return f"Error: skill '{skill_name}' not found."

        if _llm is None:
            return f"Error: LLM not configured for call_skill tool."

        parts = [_base_system_message]
        if skill.instruction:
            parts.append(skill.instruction)
        else:
            parts.append(f"You are now operating as the {skill.name} skill: {skill.description}")
        system_message = "\n\n".join(parts)

        messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=question or skill_name),
        ]
        try:
            response = await _llm.ainvoke(messages)
            return response.content or "(empty response)"
        except Exception as e:
            return f"Error invoking skill '{skill_name}': {e}"