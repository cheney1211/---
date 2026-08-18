"""
Calculator tool — safely evaluate mathematical expressions.

Uses Python's eval() with a restricted namespace (only math functions).
"""

from __future__ import annotations

import math
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register

# Build a safe namespace: math module functions + builtins
_SAFE_NAMESPACE: dict = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
_SAFE_NAMESPACE.update({
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "int": int,
    "float": float,
    "sum": sum,
    "pow": pow,
})


class CalculatorInput(BaseModel):
    """Input schema for calculate."""
    expression: str = Field(description="要计算的数学表达式，如 '2 + 3 * 4' 或 'sqrt(16) + log(100)'")


class CalculatorTool(Tool):
    name: str = "calculate"
    description: str = "计算数学表达式，支持加减乘除、三角函数、对数、幂运算等。"
    args_schema: Type[BaseModel] = CalculatorInput

    def _run(self, expression: str) -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, _SAFE_NAMESPACE)
            return str(result)
        except Exception as e:
            return f"计算 '{expression}' 失败: {e}"


register(CalculatorTool())
