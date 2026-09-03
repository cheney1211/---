"""
技能包 - 所有技能从项目 skills/ 目录中以 SKILL.md 文件形式加载。
"""
from .base import Skill
from .registry import (
    register,
    get_skill,
    get_all_skills,
    list_skills,
    get_skill_details,
    load_from_disk,
    reload_skills,
    build_skills_system_prompt,
    build_skill_instruction_prompt,
)
# 导入时从磁盘加载所有技能。
load_from_disk()
__all__ = [
    "Skill",
    "register",
    "get_skill",
    "get_all_skills",
    "list_skills",
    "get_skill_details",
    "load_from_disk",
    "reload_skills",
    "build_skills_system_prompt",
    "build_skill_instruction_prompt",
]
