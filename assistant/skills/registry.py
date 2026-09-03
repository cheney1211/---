"""
全局技能注册表。

所有技能从项目 skills/ 目录加载。
"""
from __future__ import annotations
from typing import Any, Dict, List
from .base import Skill
from .loader import load_skills_from_directory, get_skills_directory
from assistant.tools import get_tools as get_all_tool_instances
_registry: Dict[str, Skill] = {}
def register(skill: Skill) -> None:
    """注册一个技能实例。如果已存在同名技能，则覆盖。"""
    _registry[skill.name] = skill
def get_skill(name: str) -> Skill:
    """根据名称查找已注册的技能。如果未找到则抛出 ValueError。"""
    if name not in _registry:
        available = ", ".join(sorted(_registry)) or "(无)"
        raise ValueError(f"未知技能：{name!r}。可用技能：{available}")
    return _registry[name]
def get_all_skills() -> List[Skill]:
    """返回所有已注册的技能实例。"""
    return list(_registry.values())
def list_skills() -> List[Dict[str, Any]]:
    """返回已注册技能的摘要列表。"""
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
    """返回技能的详细信息，包括关联的工具元数据。"""
    skill = get_skill(name)
    tools_by_name = {t.name: t for t in get_all_tool_instances()}
    tools_payload: List[Dict[str, Any]] = []
    for tool_name in skill.tool_names:
        tool = tools_by_name.get(tool_name)
        if tool is None:
            raise ValueError(f"技能 '{skill.name}' 引用了未知工具 '{tool_name}'")
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
    """从项目 skills/ 目录加载所有技能。返回加载数量。"""
    loaded = load_skills_from_directory(get_skills_directory())
    for skill in loaded:
        register(skill)
    return len(loaded)
def reload_skills() -> int:
    """清空注册表并从磁盘重新加载所有技能。返回加载数量。"""
    _registry.clear()
    return load_from_disk()
def build_skills_system_prompt() -> str:
    """构建包含技能索引（仅名称和描述）的系统提示片段。"""
    if not _registry:
        return ""
    lines = ["你拥有以下技能："]
    for skill in _registry.values():
        lines.append(f"- {skill.name}: {skill.description}")
    return "\n".join(lines)
def build_skill_instruction_prompt(skill_name: str) -> str:
    """为特定技能构建完整的系统提示（用于第二次 LLM 调用）。"""
    skill = get_skill(skill_name)
    parts = []
    if skill.instruction:
        parts.append(skill.instruction)
    else:
        parts.append(f"你现在正在以 {skill.name} 技能运行：{skill.description}")
    return "\n".join(parts)
