"""
工具包 - 为助手提供可插拔的工具系统。

导入此包时会自动注册所有内置工具。
"""

from .base import Tool
from .confirmation import ConfirmationManager, ConfirmationRequest
from .registry import (
    register,
    get_tool,
    get_all_tools,
    get_tools,
    list_tools,
    execute_tool,
)

# 通过导入内置子包来自动注册内置工具。
from . import builtin  # noqa: F401

__all__ = [
    "Tool",
    "ConfirmationManager",
    "ConfirmationRequest",
    "register",
    "get_tool",
    "get_all_tools",
    "get_tools",
    "list_tools",
    "execute_tool",
]
