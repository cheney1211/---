"""
所有工具的基类，基于 LangChain 的 BaseTool 构建。

子类必须定义：
  - name: str              — 工具名称（供 LLM 调用）
  - description: str       — 工具描述（展示给 LLM）
  - args_schema: Type[BaseModel] — 输入参数的 Pydantic 模型
  - _run(**kwargs) -> str  — 实际执行逻辑

可选：
  - requires_confirmation: bool — 设为 True 表示危险操作，需用户确认
  - _allow_external_paths: bool — 设为 True 允许路径指向工作区外（需确认）

安全机制：
  路径校验由 LangGraph 的 path_validator 图节点统一执行，
  工具自身无需调用 validate_path()。
"""

from __future__ import annotations

from typing import ClassVar, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class Tool(BaseTool):
    """LangChain BaseTool 子类的基类。

    所有工具继承此类，只需声明 name / description / args_schema，
    并实现 _run() 即可。bind_tools() 可直接接受 Tool 实例。
    """
    requires_confirmation: bool = Field(
        default=False,
        description="执行前是否需要用户确认。"
                    "对于文件写入、Shell 命令等危险操作应设为 True。",
    )

    # 设为 True 表示允许路径指向工作区外（需用户确认）。
    # 默认为 False，path_validator 会拒绝工作区外的路径。
    # read_file 设为 True，因为它支持读取外部文件（经确认后）。
    _allow_external_paths: ClassVar[bool] = False

    def check_requires_confirmation(self, **kwargs) -> bool:
        """基于实际参数的动态确认检查。

        覆盖此方法可实现上下文相关的确认逻辑
        （例如仅在访问工作区外路径时要求确认）。
        默认实现返回静态的 requires_confirmation 值。
        """
        return self.requires_confirmation
