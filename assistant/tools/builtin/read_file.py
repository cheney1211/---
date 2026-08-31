"""
Read file tool -- read file contents with line numbers.

Safe, read-only operation. Files within the workspace are read directly.
Files outside the workspace require human confirmation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register
from ..workspace import resolve_path, is_within_workspace, get_workspace_root


class ReadFileInput(BaseModel):
    """Input schema for read_file."""
    file_path: str = Field(description="要读取的文件的绝对路径或相对于工作区的路径")
    offset: int = Field(default=0, description="起始行号（从0开始），默认为0")
    limit: int = Field(default=2000, description="最多读取的行数，默认为2000")


class ReadFileTool(Tool):
    name: str = "read_file"
    description: str = (
        "读取文件内容并返回带行号的文本。"
        "支持 offset 和 limit 参数分段读取大文件。"
        "路径相对于工作区目录，也可使用绝对路径。"
    )
    args_schema: Type[BaseModel] = ReadFileInput
    requires_confirmation: bool = False

    def check_requires_confirmation(self, **kwargs) -> bool:
        """Require confirmation when reading files outside the workspace."""
        file_path = kwargs.get("file_path", "")
        if not file_path:
            return False
        resolved = resolve_path(file_path)
        return not is_within_workspace(resolved)

    def _run(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        path = resolve_path(file_path)
        workspace = get_workspace_root()

        if not is_within_workspace(path):
            pass  # allowed with confirmation; check_requires_confirmation handles it

        if not path.exists():
            return f"错误: 文件不存在 '{file_path}'"
        if not path.is_file():
            return f"错误: 路径不是文件 '{file_path}'"

        # Detect binary files
        try:
            raw = path.read_bytes()[:8192]
            if b"\x00" in raw:
                return f"错误: 文件 '{file_path}' 是二进制文件，无法以文本方式读取"
        except Exception:
            pass

        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            return f"错误: 文件 '{file_path}' 编码不是 UTF-8，无法读取"
        except Exception as e:
            return f"错误: 读取文件 '{file_path}' 失败: {e}"

        total = len(lines)
        start = max(0, offset)
        end = min(total, start + limit)
        selected = lines[start:end]

        if not selected:
            return f"文件 '{file_path}' 共 {total} 行，指定范围 [{start}, {end}) 无内容"

        # Format with line numbers (cat -n style, 1-based)
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:6d}\t{line.rstrip()}")

        result = "\n".join(numbered)
        header = f"'{file_path}' 共 {total} 行，显示第 {start + 1}-{end} 行"
        return f"{header}\n{result}"


register(ReadFileTool())
