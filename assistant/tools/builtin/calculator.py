"""
计算器工具 -- 安全地求值数学表达式。

使用 Python 的 eval() 并限制命名空间（仅包含数学函数）。
"""

from __future__ import annotations

import math
from typing import Type

from pydantic import BaseModel, Field

from ..base import Tool
from ..registry import register

# 构建安全的命名空间：math 模块函数 + 内置函数
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
    """计算器的输入模式。"""
    expression: str = Field(description="要计算的数学表达式，如 '2 + 3 * 4' 或 'sqrt(16) + log(100)'")


class CalculatorTool(Tool):
    name: str = "calculate"
    description: str = "计算数学表达式，支持加减乘除、三角函数、对数、幂运算等。"
    args_schema: Type[BaseModel] = CalculatorInput
    requires_confirmation: bool = False

    def _run(self, expression: str) -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, _SAFE_NAMESPACE)
            return str(result)
        except Exception as e:
            return f"计算 '{expression}' 失败: {e}"


register(CalculatorTool())
