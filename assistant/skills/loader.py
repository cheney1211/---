"""
File-based skill loader.

Scans a directory for skill folders containing SKILL.md files,
parses YAML frontmatter to extract metadata, and registers them.

Directory layout:
    skills/
      calculator/
        SKILL.md
      weather/
        SKILL.md

SKILL.md format:
    ---
    name: calculator
    version: "1.0.0"
    author: builtin
    description: 数学计算能力。
    tags: [math]
    tools: [calculate]
    ---
    # 数学计算助手
    当用户需要计算时，使用 calculate 工具。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

import yaml

from .base import Skill

logger = logging.getLogger("skills.loader")

_SKILL_FILENAME = "SKILL.md"


def get_skills_directory() -> Path:
    """Return the project-level skills directory, creating it if needed."""
    project_root = Path(__file__).resolve().parent.parent.parent
    skills_dir = project_root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def parse_skill_md(content: str) -> Optional[Skill]:
    """Parse a SKILL.md string into a Skill object.

    Expects YAML frontmatter delimited by '---' at the top.
    The markdown body below the frontmatter becomes the instruction.
    Returns None if the content has no valid frontmatter.
    """
    # Match: ---\n<yaml>\n---\n<markdown body>
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        logger.warning("SKILL.md missing valid frontmatter (expected --- delimited YAML)")
        return None

    yaml_str, body = match.group(1), match.group(2).strip()

    try:
        meta = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        logger.warning("Failed to parse skill frontmatter: %s", e)
        return None

    if not isinstance(meta, dict) or "name" not in meta:
        logger.warning("Skill frontmatter missing required 'name' field")
        return None

    return Skill(
        name=meta["name"],
        description=meta.get("description", ""),
        tags=meta.get("tags") or [],
        tool_names=meta.get("tools") or [],
        instruction=body or meta.get("instruction"),
        version=str(meta.get("version", "0.1.0")),
        author=meta.get("author", "unknown"),
    )


def load_skills_from_directory(skills_dir: Path | None = None) -> List[Skill]:
    """Scan a skills directory and return parsed Skill objects.

    Looks for subdirectories containing SKILL.md.
    """
    skills_dir = skills_dir or get_skills_directory()
    if not skills_dir.is_dir():
        return []

    skills: List[Skill] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / _SKILL_FILENAME
        if not skill_file.is_file():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", skill_file, e)
            continue
        skill = parse_skill_md(content)
        if skill:
            skills.append(skill)
            logger.info("Loaded skill '%s' from %s", skill.name, skill_file)

    return skills


def create_skill_on_disk(
    name: str,
    description: str,
    tags: List[str],
    tool_names: List[str],
    instruction: str,
    version: str = "1.0.0",
    author: str = "agent",
    skills_dir: Path | None = None,
) -> Path:
    """Write a new SKILL.md to disk. Returns the path to the created file."""
    skills_dir = skills_dir or get_skills_directory()
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / _SKILL_FILENAME

    frontmatter = {
        "name": name,
        "version": version,
        "author": author,
        "description": description,
        "tags": tags,
        "tools": tool_names,
    }

    yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
    content = f"---\n{yaml_str}---\n{instruction}\n"

    skill_file.write_text(content, encoding="utf-8")
    logger.info("Created skill '%s' at %s", name, skill_file)
    return skill_file
