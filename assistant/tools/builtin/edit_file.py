"""
编辑文件工具 -- 替换文件中的指定文本。

执行精确的字符串替换。old_string 必须在文件中
唯一出现一次，编辑才能成功。
仅允许在工作区目录内操作。
执行前需要确认。
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register


class EditFileInput(BaseModel):
    """edit_file 的输入模式。"""
    file_path: str = Field(description="要编辑的文件路径（相对于工作区或绝对路径）")
    old_string: str = Field(description="要被替换的原始文本（必须在文件中唯一匹配）")
    new_string: str = Field(description="替换后的新文本")


class EditFileTool(Tool):
    name: str = "edit_file"
    description: str = (
        "编辑文件：将文件中的指定文本替换为新文本。"
        "old_string 必须在文件中精确匹配且唯一出现，否则操作失败。"
        "路径必须在工作区内，工作区外的路径会被拒绝。"
    )
    args_schema: Type[BaseModel] = EditFileInput
    requires_confirmation: bool = True

    def _run(self, file_path: str, old_string: str, new_string: str) -> str:
        # file_path 已由基类中间件（invoke → _validate_path_args）验证并解析。
        path = Path(file_path)

        if not path.exists():
            return f"错误: 文件不存在 '{file_path}'"
        if not path.is_file():
            return f"错误: 路径不是文件 '{file_path}'"

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"错误: 文件 '{file_path}' 编码不是 UTF-8，无法编辑"
        except Exception as e:
            return f"错误: 读取文件 '{file_path}' 失败: {e}"

        count = content.count(old_string)
        if count == 0:
            return f"错误: 在文件 '{file_path}' 中未找到匹配的文本。请检查 old_string 是否正确。"
        if count > 1:
            return (
                f"错误: old_string 在文件中匹配了 {count} 处，要求唯一匹配。"
                "请提供更多上下文使匹配唯一。"
            )

        new_content = content.replace(old_string, new_string, 1)

        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return f"错误: 写入文件 '{file_path}' 失败: {e}"

        return f"成功: 已编辑文件 '{file_path}'，替换了 1 处文本。"


register(EditFileTool())
