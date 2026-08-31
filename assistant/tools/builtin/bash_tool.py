"""
Bash tool -- execute shell commands.

Captures stdout and stderr, with configurable timeout.
Output is truncated to prevent LLM context overflow.
Working directory is set to the workspace root.
Commands that attempt to cd outside the workspace are blocked.
Requires confirmation before execution.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register
from ..workspace import get_workspace_root, is_within_workspace, get_platform_hint

_MAX_OUTPUT = 4000  # characters


class BashInput(BaseModel):
    """Input schema for bash."""
    command: str = Field(description="要执行的 Shell 命令")
    timeout: int = Field(default=30, description="超时时间（秒），默认30秒")


def _check_cd_targets(command: str, workspace: Path) -> str | None:
    """Parse cd commands and check if any target is outside the workspace.

    Returns an error message if a forbidden cd is found, None otherwise.
    Handles: cd path, cd "path", pushd path
    """
    # Match cd and pushd commands
    pattern = r'(?:cd|pushd)\s+["\']?([^"\';\|&\n]+?)["\']?\s*(?:;|$|&&|\|\|)'
    for match in re.finditer(pattern, command, re.IGNORECASE):
        target = match.group(1).strip()
        if not target or target == "-":
            continue
        # Skip flags like /D
        if target.startswith("/") and len(target) == 2:
            continue

        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = (workspace / target_path).resolve()
        else:
            target_path = target_path.resolve()

        if not is_within_workspace(target_path):
            return (
                f"错误: 禁止切换到工作区外的目录 '{target}'。"
                f"工作区根目录: {workspace}"
            )
    return None


class BashTool(Tool):
    name: str = "bash"
    description: str = (
        "执行 Shell 命令并返回输出。"
        "支持文件操作、git、python 脚本等。"
        "工作目录固定为工作区根目录，禁止切换到工作区外。"
        f"{get_platform_hint()}"
    )
    args_schema: Type[BaseModel] = BashInput
    requires_confirmation: bool = True

    def _run(self, command: str, timeout: int = 30) -> str:
        workspace = get_workspace_root()

        # Check for forbidden cd targets
        cd_error = _check_cd_targets(command, workspace)
        if cd_error:
            return cd_error

        kwargs = {
            "shell": True,
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "cwd": str(workspace),
        }

        try:
            result = subprocess.run(command, **kwargs)
        except subprocess.TimeoutExpired:
            return f"错误: 命令执行超时（{timeout}秒）: {command}"
        except Exception as e:
            return f"错误: 执行命令失败: {e}"

        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")

        output = "\n".join(parts).strip() if parts else "(无输出)"

        # Truncate if too long
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n... (输出已截断，共 {len(output)} 字符)"

        exit_info = f"[exit code: {result.returncode}]"
        return f"{exit_info}\n{output}"


register(BashTool())
