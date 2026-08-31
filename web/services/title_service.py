"""Auto-generate session titles via a lightweight LLM call."""

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
    """Return (provider_name, model_override) for title generation.

    Reads TITLE_PROVIDER / TITLE_MODEL env vars; falls back to the main
    chat provider when not set.
    """
    provider = os.getenv("TITLE_PROVIDER") or get_default_provider_name()
    model = os.getenv("TITLE_MODEL") or None
    return provider, model


async def generate_title(
    user_msg: str,
    assistant_msg: str,
) -> str | None:
    """Generate a concise title from the first Q&A pair.

    Returns the title string on success, or ``None`` when the feature is
    disabled or an error occurs.  Errors are logged but never raised so
    that callers can treat this as a best-effort side effect.
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
        # Clamp to 30 chars as a safety net
        return title[:30]
    except Exception:
        logger.exception("Failed to generate session title")
        return None
