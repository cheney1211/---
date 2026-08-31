"""
多模型注册中心。

支持两种 provider 类型：
1. 内置特殊 provider（ollama、dummy）—— 有独立适配器逻辑
2. 自定义 OpenAI 兼容 provider —— 通过环境变量动态配置，无需预注册

用户只需设置环境变量即可添加任意 OpenAI 兼容模型：
    LLM_PROVIDER=my-model
    my-model_API_KEY=sk-xxx
    my-model_MODEL=gpt-4o
    my-model_BASE_URL=https://api.example.com/v1
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from .base import LLMAdapter
from .langgraph_provider import LangGraphProvider

# 项目根目录（web/llm/ -> web/ -> 项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PROMPT_FILE = _PROJECT_ROOT / "assistant" / "prompts" / "system_prompt.md"


# ---------------------------------------------------------------------------
# 环境变量读取
# ---------------------------------------------------------------------------

def _read_env(name: str) -> dict:
    """读取 {NAME}_API_KEY、{NAME}_MODEL、{NAME}_BASE_URL 环境变量。

    对于自定义 provider，API_KEY 必填；MODEL 和 BASE_URL 可选。
    """
    prefix = name.upper()
    api_key = os.getenv(f"{prefix}_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"环境变量 {prefix}_API_KEY 未设置（provider '{name}' 需要）"
        )
    return {
        "api_key": api_key,
        "model": os.getenv(f"{prefix}_MODEL") or "",
        "base_url": os.getenv(f"{prefix}_BASE_URL") or None,
    }


# ---------------------------------------------------------------------------
# 内置适配器构建
# ---------------------------------------------------------------------------

def _build_openai_adapter(name: str) -> LLMAdapter:
    """从环境变量构建 OpenAI 兼容适配器。"""
    from .openai_adapter import OpenAIAdapter

    cfg = _read_env(name)
    return OpenAIAdapter(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url"),
    )


def _build_ollama_adapter() -> LLMAdapter:
    """构建 Ollama 适配器（不需要 API key）。"""
    from .ollama_adapter import OllamaAdapter

    base_url = os.getenv("OLLAMA_BASE_URL") or None
    model = os.getenv("OLLAMA_MODEL") or "qwen2.5:7b"
    return OllamaAdapter(model=model, base_url=base_url)


def _build_dummy_adapter() -> LLMAdapter:
    """构建测试用回显适配器。"""
    from .dummy_adapter import DummyAdapter

    return DummyAdapter()


# ---------------------------------------------------------------------------
# 适配器解析
# ---------------------------------------------------------------------------

def get_adapter(
    name: str,
    *,
    model: str | None = None,
) -> LLMAdapter:
    """根据 provider 名称构建适配器实例。

    内置 provider（ollama、dummy）使用专用适配器；
    其他名称视为 OpenAI 兼容 provider，从 {NAME}_* 环境变量读取配置。
    """
    name = name.strip().lower()

    if name == "dummy":
        return _build_dummy_adapter()

    if name == "ollama":
        return _build_ollama_adapter()

    # 所有其他 provider：OpenAI 兼容，动态读取环境变量
    adapter = _build_openai_adapter(name)
    # 如果调用方指定了 model 覆盖，需要替换底层 LLM 的 model
    if model:
        from .openai_adapter import OpenAIAdapter

        cfg = _read_env(name)
        adapter = OpenAIAdapter(
            model=model,
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url"),
        )
    return adapter


def get_provider(
    name: str,
    *,
    model: str | None = None,
    system_message: str | None = None,
    tools: list | None = None,
    confirmation_mode: str = "confirm",
    **kwargs,
) -> LangGraphProvider:
    """构建带 LangGraph 的 agent-ready provider。"""
    if name == "dummy":
        return _build_dummy_provider(system_message=system_message)

    adapter = get_adapter(name, model=model)
    return LangGraphProvider(
        llm=adapter.llm,
        tools=tools or [],
        system_message=system_message,
        confirmation_mode=confirmation_mode,
    )


def _build_dummy_provider(*, system_message: str | None = None) -> LangGraphProvider:
    """构造一个不依赖 LLM 的回显 provider，用于本地测试。"""
    from langchain_core.language_models import FakeListChatModel

    fake_llm = FakeListChatModel(responses=["(dummy) 收到你的消息了。"])
    return LangGraphProvider(
        llm=fake_llm,
        tools=[],
        system_message=system_message,
    )


# ---------------------------------------------------------------------------
# Provider 信息
# ---------------------------------------------------------------------------

def get_default_provider_name() -> str:
    """返回默认 provider 名称（读取 LLM_PROVIDER 环境变量，默认 openai）。"""
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def get_default_system_message() -> str:
    """返回默认系统提示词。

    从 SYSTEM_PROMPT_FILE 环境变量指定的文件读取，
    未设置则读取 assistant/prompts/default.md。
    """
    prompt_path = os.getenv("SYSTEM_PROMPT_FILE")
    prompt_file = Path(prompt_path) if prompt_path else _DEFAULT_PROMPT_FILE
    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "你叫coco，根据用户给的消息，帮助用户解决问题，能用工具解决的问题都必须使用工具，语气要温和。"


def list_providers() -> List[Dict[str, Any]]:
    """返回当前可用的 provider 列表。

    包含内置特殊 provider 和当前通过环境变量配置的默认 provider。
    """
    result = [
        {
            "name": "ollama",
            "description": "本地 Ollama 模型（不需要 API key）",
            "default_model": "qwen2.5:7b",
            "env_keys": ["OLLAMA_MODEL", "OLLAMA_BASE_URL"],
        },
        {
            "name": "dummy",
            "description": "测试用回显适配器（不需要 API key）",
            "default_model": "dummy",
            "env_keys": [],
        },
    ]

    # 尝试读取当前默认 provider 的配置
    default_name = get_default_provider_name()
    if default_name not in ("ollama", "dummy"):
        prefix = default_name.upper()
        model = os.getenv(f"{prefix}_MODEL") or ""
        has_key = bool(os.getenv(f"{prefix}_API_KEY"))
        result.append({
            "name": default_name,
            "description": f"OpenAI 兼容模型（通过 {prefix}_* 环境变量配置）",
            "default_model": model,
            "env_keys": [f"{prefix}_API_KEY", f"{prefix}_MODEL", f"{prefix}_BASE_URL"],
            "configured": has_key,
        })

    return result
