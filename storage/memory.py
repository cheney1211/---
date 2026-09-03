"""
记忆管理器 —— 处理以 Markdown 文件存储的项目专属长期记忆。

记忆文件位置：
- 项目记忆：<project_root_path>/.agent/memory.md
- 全局记忆：<workspace_root>/.agent/memory.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# 默认记忆目录名
MEMORY_DIR = ".agent"
MEMORY_FILE = "memory.md"

# 默认记忆内容模板
DEFAULT_MEMORY_CONTENT = """# 项目记忆

## 项目信息
<!-- 记录项目的基本信息，如技术栈、架构等 -->

## 编码规范
<!-- 记录项目的编码规范和约定 -->

## 常用命令
<!-- 记录常用的构建、测试、部署命令 -->

## 注意事项
<!-- 记录需要特别注意的事项 -->

## 历史决策
<!-- 记录重要的技术决策和原因 -->
"""


def get_memory_path(project_root: Path) -> Path:
    """获取项目的记忆文件路径。"""
    return project_root / MEMORY_DIR / MEMORY_FILE


def get_global_memory_path(workspace_root: Path) -> Path:
    """获取全局记忆文件路径。"""
    return workspace_root / MEMORY_DIR / MEMORY_FILE


def ensure_memory_dir(project_root: Path) -> Path:
    """确保 .agent 目录存在并返回其路径。"""
    memory_dir = project_root / MEMORY_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def read_memory(project_root: Path) -> Optional[str]:
    """读取项目的记忆文件内容。

    如果文件不存在则返回 None。
    """
    memory_path = get_memory_path(project_root)
    if not memory_path.exists():
        return None
    try:
        return memory_path.read_text(encoding="utf-8")
    except Exception:
        return None


def write_memory(project_root: Path, content: str) -> bool:
    """将内容写入项目的记忆文件。

    成功则返回 True。
    """
    try:
        ensure_memory_dir(project_root)
        memory_path = get_memory_path(project_root)
        memory_path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def append_to_memory(project_root: Path, content: str) -> bool:
    """向项目的记忆文件追加内容。

    成功则返回 True。
    """
    try:
        ensure_memory_dir(project_root)
        memory_path = get_memory_path(project_root)

        if memory_path.exists():
            existing = memory_path.read_text(encoding="utf-8")
            new_content = existing.rstrip() + "\n\n" + content
        else:
            new_content = DEFAULT_MEMORY_CONTENT + "\n\n" + content

        memory_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


def init_memory(project_root: Path) -> bool:
    """如果记忆文件不存在，则使用默认内容初始化。

    成功或文件已存在则返回 True。
    """
    memory_path = get_memory_path(project_root)
    if memory_path.exists():
        return True
    return write_memory(project_root, DEFAULT_MEMORY_CONTENT)


def read_global_memory(workspace_root: Path) -> Optional[str]:
    """读取全局记忆文件内容。

    如果文件不存在则返回 None。
    """
    memory_path = get_global_memory_path(workspace_root)
    if not memory_path.exists():
        return None
    try:
        return memory_path.read_text(encoding="utf-8")
    except Exception:
        return None


def write_global_memory(workspace_root: Path, content: str) -> bool:
    """将内容写入全局记忆文件。

    成功则返回 True。
    """
    try:
        memory_dir = workspace_root / MEMORY_DIR
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_path = get_global_memory_path(workspace_root)
        memory_path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False
