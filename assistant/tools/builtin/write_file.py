"""
写入文件工具 -- 创建或覆盖文件。

如果父目录不存在会自动创建。
仅允许在工作区目录内操作。
执行前需要确认。
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register


class WriteFileInput(BaseModel):
    """write_file 的输入模式。"""
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
        # file_path 已由基类中间件（invoke → _validate_path_args）验证并解析。
        path = Path(file_path)

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
