"""
Tool package — provides a pluggable tool system for the assistant.

Importing this package auto-registers all built-in tools.
"""

from .base import Tool
from .registry import (
    register,
    get_tool,
    get_all_tools,
    get_tools,
    list_tools,
    execute_tool,
)

# Auto-register built-in tools by importing the builtin sub-package.
from . import builtin  # noqa: F401

__all__ = [
    "Tool",
    "register",
    "get_tool",
    "get_all_tools",
    "get_tools",
    "list_tools",
    "execute_tool",
]