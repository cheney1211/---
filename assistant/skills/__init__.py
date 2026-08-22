"""
Skills package - all skills are loaded from project skills/ directory as SKILL.md files.
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
# Load all skills from disk on import.
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
