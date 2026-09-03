"""通过轻量级 LLM 调用自动生成会话标题。"""

from __future__ import annotations

import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage

from web.llm import get_adapter, get_default_provider_name

logger = logging.getLogger(__name__)

_TITLE_PROMPT = (
    "根据以下用户和助手的对话内容，生成一个简短精准的会话标题。"
    "要求：3-15个字，只输出标题本身，不要任何引号、标点前缀或解释。"
)


def _is_enabled() -> bool:
    return os.getenv("AUTO_TITLE_ENABLED", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )


def _get_title_provider() -> tuple[str, str | None]:
    """返回用于标题生成的 (provider_name, model_override)。

    读取 TITLE_PROVIDER / TITLE_MODEL 环境变量；如果未设置则回退到
    主聊天提供者。
    """
    provider = os.getenv("TITLE_PROVIDER") or get_default_provider_name()
    model = os.getenv("TITLE_MODEL") or None
    return provider, model


async def generate_title(
    user_msg: str,
    assistant_msg: str,
) -> str | None:
    """根据第一组问答对生成简洁的标题。

    成功时返回标题字符串，功能禁用或发生错误时返回 ``None``。
    错误会被记录日志但不会抛出异常，以便调用方可以将此视为
    尽力而为的副作用。
    """
    if not _is_enabled():
        return None

    try:
        provider_name, model = _get_title_provider()
        adapter = get_adapter(provider_name, model=model)
        llm = adapter.llm

        user_content = (
            f"用户：{user_msg[:500]}\n\n助手：{assistant_msg[:500]}"
        )
        messages = [
            SystemMessage(content=_TITLE_PROMPT),
            HumanMessage(content=user_content),
        ]
        result = await llm.ainvoke(messages)
        title = (result.content or "").strip().strip('"').strip("'")
        if not title:
            return None
        # 限制最多30个字符作为安全措施
        return title[:30]
    except Exception:
        logger.exception("生成会话标题失败")
        return None
