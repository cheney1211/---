"""
Base class for all tools, built on LangChain's BaseTool.

Subclasses must define:
  - name: str              -- tool name (used by LLM to call)
  - description: str       -- tool description (shown to LLM)
  - args_schema: Type[BaseModel] -- Pydantic model for input parameters
  - _run(**kwargs) -> str  -- actual execution logic

Optional:
  - requires_confirmation: bool -- set True for dangerous operations
"""

from __future__ import annotations

from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class Tool(BaseTool):
    """LangChain BaseTool subclass base class.

    All tools inherit this class, just declare name / description / args_schema,
    and implement _run(). bind_tools() can directly accept Tool instances.
    """
    requires_confirmation: bool = Field(
        default=False,
        description="Whether this tool requires human confirmation before execution. "
                    "Set to True for dangerous operations like file writes or shell commands.",
    )

    def check_requires_confirmation(self, **kwargs) -> bool:
        """Dynamic confirmation check based on actual arguments.

        Override this method to enable context-dependent confirmation logic
        (e.g., require confirmation only when accessing paths outside the workspace).
        The default implementation returns the static requires_confirmation value.
        """
        return self.requires_confirmation