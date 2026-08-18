"""
Global tool registry.

Tools register themselves at import time via register().
The registry provides lookup, listing, and BaseTool exports.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .base import Tool

_registry: Dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Register a tool instance.  Overwrites any previous tool with the same name."""
    _registry[tool.name] = tool


def get_tool(name: str) -> Tool:
    """Look up a registered tool by name.  Raises ValueError if not found."""
    if name not in _registry:
        available = ", ".join(sorted(_registry)) or "(none)"
        raise ValueError(f"Unknown tool: {name!r}. Available: {available}")
    return _registry[name]


def get_all_tools() -> List[Tool]:
    """Return all registered BaseTool instances."""
    return list(_registry.values())


def get_tools() -> List[Tool]:
    """Return all registered BaseTool instances (alias for get_all_tools)."""
    return get_all_tools()


def list_tools() -> List[Dict[str, str]]:
    """Return a summary list of registered tools (name + description)."""
    return [{"name": t.name, "description": t.description} for t in _registry.values()]


def execute_tool(name: str, arguments: Any) -> str:
    """Execute a tool by name with the given arguments.

    *arguments* can be a dict (already parsed) or a JSON string.
    Returns the tool's string result, or an error message on failure.
    """
    tool = get_tool(name)
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return f"Error: invalid JSON arguments for tool '{name}': {arguments}"
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        return tool.invoke(arguments)
    except Exception as e:
        return f"Error executing tool '{name}': {e}"