"""
读取文件工具 -- 读取文件内容并显示行号。

安全的只读操作。工作区内的文件直接读取。
工作区外的文件需要人工确认。
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register


class ReadFileInput(BaseModel):
    """read_file 的输入模式。"""
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
    _allow_external_paths: bool = True  # 允许在确认后读取工作区外的文件

    def check_requires_confirmation(self, **kwargs) -> bool:
        """读取工作区外的文件时需要确认。"""
        from ..workspace import is_within_workspace, resolve_path

        file_path = kwargs.get("file_path", "")
        if not file_path:
            return False
        resolved = resolve_path(file_path)
        return not is_within_workspace(resolved)

    def _run(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        # file_path 已由基类中间件（invoke → _validate_path_args → resolve_path）解析。
        path = Path(file_path)

        if not path.exists():
            return f"错误: 文件不存在 '{file_path}'"
        if not path.is_file():
            return f"错误: 路径不是文件 '{file_path}'"

        # 检测二进制文件
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

        # 格式化行号（cat -n 风格，从 1 开始）
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:6d}\t{line.rstrip()}")

        result = "\n".join(numbered)
        header = f"'{file_path}' 共 {total} 行，显示第 {start + 1}-{end} 行"
        return f"{header}\n{result}"


register(ReadFileTool())
