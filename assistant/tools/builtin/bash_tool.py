"""
Bash 工具 -- 执行 Shell 命令。

捕获标准输出和标准错误，支持可配置的超时时间。
输出会被截断以防止 LLM 上下文溢出。
工作目录设置为工作区根目录。
禁止切换到工作区外的目录。
执行前需要确认。
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

_MAX_OUTPUT = 4000  # 字符数


class BashInput(BaseModel):
    """bash 命令的输入模式。"""
    command: str = Field(description="要执行的 Shell 命令")
    timeout: int = Field(default=30, description="超时时间（秒），默认30秒")


def _check_cd_targets(command: str, workspace: Path) -> str | None:
    """解析 cd 命令并检查是否有目标路径在工作区外。

    如果发现禁止的 cd 操作则返回错误消息，否则返回 None。
    处理的命令格式：cd path, cd "path", pushd path
    """
    # 匹配 cd 和 pushd 命令
    pattern = r'(?:cd|pushd)\s+["\']?([^"\';\|&\n]+?)["\']?\s*(?:;|$|&&|\|\|)'
    for match in re.finditer(pattern, command, re.IGNORECASE):
        target = match.group(1).strip()
        if not target or target == "-":
            continue
        # 跳过类似 /D 的标志参数
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

        # 检查是否有禁止的 cd 目标
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

        # 过长则截断
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + f"\n... (输出已截断，共 {len(output)} 字符)"

        exit_info = f"[exit code: {result.returncode}]"
        return f"{exit_info}\n{output}"


register(BashTool())
