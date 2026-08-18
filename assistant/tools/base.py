"""
Base class for all tools, built on LangChain's BaseTool.

Subclasses must define:
  - name: str              — 工具名称（LLM 用来调用）
  - description: str       — 工具描述（展示给 LLM）
  - args_schema: Type[BaseModel] — Pydantic 模型，定义输入参数
  - _run(**kwargs) -> str  — 实际执行逻辑
"""

from __future__ import annotations

from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel


class Tool(BaseTool):
    """LangChain BaseTool 的子类基类。

    所有工具继承此类后，只需声明 name / description / args_schema，
    并实现 _run() 即可。bind_tools() 可以直接接受 Tool 实例。
    """
    pass
