"""技能路由工具。

当 LLM 决定用户的请求应由特定技能处理时，
会调用此工具。该工具内部将完整的技能指令注入 LLM 并调用，
然后将结果作为普通工具响应返回。
routes.py 中不会发起第二次 LLM 调用 -- 一切在同一个图循环中完成。
"""

from __future__ import annotations

from typing import Optional, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..base import Tool

# 模块级引用，由 provider 在启动时配置。
_llm: Optional[BaseChatModel] = None
_base_system_message: str = ""


def configure(llm: BaseChatModel, base_system_message: str) -> None:
    """启动时调用一次，注入 LLM 和系统消息。"""
    global _llm, _base_system_message
    _llm = llm
    _base_system_message = base_system_message


class CallSkillInput(BaseModel):
    """call_skill 的输入模式。"""
    skill_name: str = Field(description="要激活的技能名称。")
    question: str = Field(
        default="",
        description="要传递给技能的用户原始问题。",
    )


class CallSkillTool(Tool):
    name: str = "call_skill"
    description: str = (
        "激活一个技能来处理用户的请求。"
        "当用户的问题匹配某个可用技能时使用此工具。"
        "在 'question' 字段中传入用户的原始问题。"
    )
    args_schema: Type[BaseModel] = CallSkillInput

    def _run(self, skill_name: str, question: str = "") -> str:
        from assistant.skills import get_skill

        try:
            skill = get_skill(skill_name)
        except ValueError:
            return f"错误：未找到技能 '{skill_name}'。"

        if _llm is None:
            return "错误：call_skill 工具未配置 LLM。"

        # 构建系统消息：基础消息 + 完整技能指令
        parts = [_base_system_message]
        if skill.instruction:
            parts.append(skill.instruction)
        else:
            parts.append(f"你现在以 {skill.name} 技能的身份运行：{skill.description}")
        system_message = "\n\n".join(parts)

        # 使用技能上下文调用 LLM
        messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=question or skill_name),
        ]
        try:
            response = _llm.invoke(messages)
            return response.content or "（空响应）"
        except Exception as e:
            return f"调用技能 '{skill_name}' 时出错：{e}"

    async def _arun(self, skill_name: str, question: str = "") -> str:
        from assistant.skills import get_skill

        try:
            skill = get_skill(skill_name)
        except ValueError:
            return f"错误：未找到技能 '{skill_name}'。"

        if _llm is None:
            return "错误：call_skill 工具未配置 LLM。"

        parts = [_base_system_message]
        if skill.instruction:
            parts.append(skill.instruction)
        else:
            parts.append(f"你现在以 {skill.name} 技能的身份运行：{skill.description}")
        system_message = "\n\n".join(parts)

        messages = [
            SystemMessage(content=system_message),
            HumanMessage(content=question or skill_name),
        ]
        try:
            response = await _llm.ainvoke(messages)
            return response.content or "（空响应）"
        except Exception as e:
            return f"调用技能 '{skill_name}' 时出错：{e}"
