"""
多模型注册中心。

支持两种 provider 类型：
1. 内置特殊 provider（ollama、dummy）—— 有独立适配器逻辑
2. 自定义 OpenAI 兼容 provider —— 通过 config.json 或环境变量配置

配置优先级：config.json > 环境变量
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
# 配置读取（config.json 优先，回退到环境变量）
# ---------------------------------------------------------------------------

def _read_provider_config(name: str) -> dict:
    """读取 provider 配置，config.json 优先，回退到环境变量。"""
    from web.config import get_llm_config

    # 如果请求的是当前活跃 provider，直接使用 config 的合并结果
    current = get_llm_config()
    if current["provider"] == name:
        api_key = current["api_key"]
        if not api_key and name not in ("ollama", "dummy"):
            raise RuntimeError(f"provider '{name}' 的 API key 未配置")
        return {
            "api_key": api_key,
            "model": current["model"],
            "base_url": current["base_url"] or None,
        }

    # 非当前 provider，回退到环境变量
    prefix = name.upper()
    api_key = os.getenv(f"{prefix}_API_KEY", "")
    if not api_key and name not in ("ollama", "dummy"):
        raise RuntimeError(f"环境变量 {prefix}_API_KEY 未设置（provider '{name}' 需要）")
    return {
        "api_key": api_key,
        "model": os.getenv(f"{prefix}_MODEL") or "",
        "base_url": os.getenv(f"{prefix}_BASE_URL") or None,
    }


# ---------------------------------------------------------------------------
# 内置适配器构建
# ---------------------------------------------------------------------------

def _build_openai_adapter(name: str) -> LLMAdapter:
    """从配置构建 OpenAI 兼容适配器。"""
    from .openai_adapter import OpenAIAdapter

    cfg = _read_provider_config(name)
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

    # 所有其他 provider：OpenAI 兼容
    adapter = _build_openai_adapter(name)
    # 如果调用方指定了 model 覆盖，需要替换底层 LLM 的 model
    if model:
        from .openai_adapter import OpenAIAdapter

        cfg = _read_provider_config(name)
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
    workspace_root: str = "",
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
        workspace_root=workspace_root,
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
# Provider 目录（下拉选择 + 默认值）
# ---------------------------------------------------------------------------

PROVIDER_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "openai",
        "label": "OpenAI",
        "description": "OpenAI 官方 API",
        "default_base_url": "https://api.openai.com/v1",
        "recommended_models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o3", "o4-mini"],
        "requires_api_key": True,
    },
    {
        "name": "deepseek",
        "label": "DeepSeek",
        "description": "DeepSeek AI",
        "default_base_url": "https://api.deepseek.com/v1",
        "recommended_models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        "requires_api_key": True,
    },
    {
        "name": "mimo",
        "label": "Mimo (小米)",
        "description": "小米 Mimo 大模型",
        "default_base_url": "https://api.xiaomimimo.com/v1",
        "recommended_models": ["mimo-v2.5", "mimo-v2.5-pro"],
        "requires_api_key": True,
    },
    {
        "name": "anthropic",
        "label": "Anthropic",
        "description": "Claude 系列模型",
        "default_base_url": "https://api.anthropic.com/v1",
        "recommended_models": ["claude-sonnet-4-20250514", "claude-haiku-4-20250514"],
        "requires_api_key": True,
    },
    {
        "name": "ollama",
        "label": "Ollama (本地)",
        "description": "本地 Ollama 推理，不需要 API Key",
        "default_base_url": "http://localhost:11434",
        "recommended_models": ["qwen2.5:7b", "llama3.1:8b", "deepseek-r1:7b", "mistral:7b"],
        "requires_api_key": False,
    },
    {
        "name": "openai_compatible",
        "label": "OpenAI 兼容 (自定义)",
        "description": "任何 OpenAI 兼容的 API 端点",
        "default_base_url": "",
        "recommended_models": [],
        "requires_api_key": True,
    },
]


def get_default_provider_name() -> str:
    """返回默认 provider 名称（config.json 优先，回退到环境变量）。"""
    from web.config import get_llm_config
    return get_llm_config()["provider"]


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
    """返回当前可用的 provider 列表。"""
    from web.config import get_llm_config, mask_api_key

    result = [
        {
            "name": "ollama",
            "description": "本地 Ollama 模型（不需要 API key）",
            "default_model": "qwen2.5:7b",
        },
        {
            "name": "dummy",
            "description": "测试用回显适配器（不需要 API key）",
            "default_model": "dummy",
        },
    ]

    # 当前活跃 provider 的实际配置
    llm_cfg = get_llm_config()
    default_name = llm_cfg["provider"]
    if default_name not in ("ollama", "dummy"):
        result.append({
            "name": default_name,
            "description": "OpenAI 兼容模型",
            "default_model": llm_cfg["model"],
            "configured": bool(llm_cfg["api_key"]),
        })

    return result
