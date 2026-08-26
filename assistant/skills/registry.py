"""
Global skill registry.

All skills are loaded from the project skills/ directory.
"""
from __future__ import annotations
from typing import Any, Dict, List
from .base import Skill
from .loader import load_skills_from_directory, get_skills_directory
from assistant.tools import get_tools as get_all_tool_instances
_registry: Dict[str, Skill] = {}
def register(skill: Skill) -> None:
    """Register a skill instance. Overwrites any previous skill with the same name."""
    _registry[skill.name] = skill
def get_skill(name: str) -> Skill:
    """Look up a registered skill by name. Raises ValueError if not found."""
    if name not in _registry:
        available = ", ".join(sorted(_registry)) or "(none)"
        raise ValueError(f"Unknown skill: {name!r}. Available: {available}")
    return _registry[name]
def get_all_skills() -> List[Skill]:
    """Return all registered skill instances."""
    return list(_registry.values())
def list_skills() -> List[Dict[str, Any]]:
    """Return a summary list of registered skills."""
    return [
        {
            "name": s.name,
            "description": s.description,
            "tags": list(s.tags),
            "tool_names": list(s.tool_names),
            "version": s.version,
            "author": s.author,
        }
        for s in _registry.values()
    ]
def get_skill_details(name: str) -> Dict[str, Any]:
    """Return detailed skill info including associated tool metadata."""
    skill = get_skill(name)
    tools_by_name = {t.name: t for t in get_all_tool_instances()}
    tools_payload: List[Dict[str, Any]] = []
    for tool_name in skill.tool_names:
        tool = tools_by_name.get(tool_name)
        if tool is None:
            raise ValueError(f"Skill '{skill.name}' references unknown tool '{tool_name}'")
        tools_payload.append({"name": tool.name, "description": tool.description})
    return {
        "name": skill.name,
        "description": skill.description,
        "tags": list(skill.tags),
        "tool_names": list(skill.tool_names),
        "instruction": skill.instruction,
        "version": skill.version,
        "author": skill.author,
        "tools": tools_payload,
    }
def load_from_disk() -> int:
    """Load all skills from the project skills/ directory. Returns count."""
    loaded = load_skills_from_directory(get_skills_directory())
    for skill in loaded:
        register(skill)
    return len(loaded)
def reload_skills() -> int:
    """Clear registry and reload all skills from disk. Returns count."""
    _registry.clear()
    return load_from_disk()
def build_skills_system_prompt() -> str:
    """Build a system prompt fragment with skill index (name + description only)."""
    if not _registry:
        return ""
    lines = ["you have the following skills:"]
    for skill in _registry.values():
        lines.append(f"- {skill.name}: {skill.description}")
    return "\n".join(lines)
def build_skill_instruction_prompt(skill_name: str) -> str:
    """Build a full system prompt for a specific skill (second LLM call)."""
    skill = get_skill(skill_name)
    parts = []
    if skill.instruction:
        parts.append(skill.instruction)
    else:
        parts.append(f"you are now operating as the {skill.name} skill: {skill.description}")
    return "\n".join(parts)
