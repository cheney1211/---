"""
基于文件的技能加载器。

扫描目录中包含 SKILL.md 文件的技能文件夹，
解析 YAML frontmatter 以提取元数据，并将其注册。

目录结构：
    skills/
      calculator/
        SKILL.md
      weather/
        SKILL.md

SKILL.md 格式：
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
    """返回项目级别的技能目录，如果不存在则创建。"""
    project_root = Path(__file__).resolve().parent.parent.parent
    skills_dir = project_root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def parse_skill_md(content: str) -> Optional[Skill]:
    """将 SKILL.md 字符串解析为 Skill 对象。

    期望顶部以 '---' 分隔的 YAML frontmatter。
    frontmatter 下方的 markdown 正文将作为指令内容。
    如果内容没有有效的 frontmatter，则返回 None。
    """
    # 匹配：---\n<yaml>\n---\n<markdown正文>
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        logger.warning("SKILL.md 缺少有效的 frontmatter（期望以 --- 分隔的 YAML）")
        return None

    yaml_str, body = match.group(1), match.group(2).strip()

    try:
        meta = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        logger.warning("解析技能 frontmatter 失败：%s", e)
        return None

    if not isinstance(meta, dict) or "name" not in meta:
        logger.warning("技能 frontmatter 缺少必需的 'name' 字段")
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
    """扫描技能目录并返回解析后的 Skill 对象列表。

    查找包含 SKILL.md 的子目录。
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
            logger.warning("读取 %s 失败：%s", skill_file, e)
            continue
        skill = parse_skill_md(content)
        if skill:
            skills.append(skill)
            logger.info("已从 %s 加载技能 '%s'", skill_file, skill.name)

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
    """将新的 SKILL.md 写入磁盘。返回所创建文件的路径。"""
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
    logger.info("已创建技能 '%s'，路径为 %s", name, skill_file)
    return skill_file
