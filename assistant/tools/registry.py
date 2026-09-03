"""
全局工具注册表。

工具在导入时通过 register() 自注册。
注册表提供查找、列举和 BaseTool 导出功能。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .base import Tool

_registry: Dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """注册一个工具实例。若已存在同名工具则覆盖。"""
    _registry[tool.name] = tool


def get_tool(name: str) -> Tool:
    """按名称查找已注册的工具。未找到时抛出 ValueError。"""
    if name not in _registry:
        available = ", ".join(sorted(_registry)) or "(无)"
        raise ValueError(f"未知工具: {name!r}。可用工具: {available}")
    return _registry[name]


def get_all_tools() -> List[Tool]:
    """返回所有已注册的 BaseTool 实例。"""
    return list(_registry.values())


def get_tools() -> List[Tool]:
    """返回所有已注册的 BaseTool 实例（get_all_tools 的别名）。"""
    return get_all_tools()


def list_tools() -> List[Dict[str, str]]:
    """返回已注册工具的摘要列表（名称 + 描述）。"""
    return [{"name": t.name, "description": t.description} for t in _registry.values()]


def execute_tool(name: str, arguments: Any) -> str:
    """按名称执行工具并传入参数。

    *arguments* 可以是 dict（已解析）或 JSON 字符串。
    返回工具的字符串结果，失败时返回错误信息。
    """
    tool = get_tool(name)
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return f"错误: 工具 '{name}' 的参数不是有效的 JSON: {arguments}"
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        return tool.invoke(arguments)
    except Exception as e:
        return f"执行工具 '{name}' 时出错: {e}"
