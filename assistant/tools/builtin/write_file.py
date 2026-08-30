"""
Write file tool -- create or overwrite a file.

Automatically creates parent directories if they don't exist.
Only allowed within the workspace directory.
Requires confirmation before execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register
from ..workspace import validate_path


class WriteFileInput(BaseModel):
    """Input schema for write_file."""
    file_path: str = Field(description="要写入的文件路径（相对于工作区或绝对路径）")
    content: str = Field(description="要写入的文件内容")


class WriteFileTool(Tool):
    name: str = "write_file"
    description: str = (
        "创建新文件或覆盖已有文件的全部内容。"
        "如果父目录不存在会自动创建。"
        "路径必须在工作区内，工作区外的路径会被拒绝。"
    )
    args_schema: Type[BaseModel] = WriteFileInput
    requires_confirmation: bool = True

    def _run(self, file_path: str, content: str) -> str:
        try:
            path = validate_path(file_path)
        except ValueError as e:
            return f"错误: {e}"

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"错误: 创建目录失败 '{path.parent}': {e}"

        existed = path.exists()

        try:
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"错误: 写入文件 '{file_path}' 失败: {e}"

        action = "覆盖" if existed else "创建"
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"成功: 已{action}文件 '{file_path}'（共 {lines} 行）"


register(WriteFileTool())
