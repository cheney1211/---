"""
Multi-model registry.

Central place for registering and resolving LLM adapters by provider name.

Usage:
    from web.llm.registry import get_adapter, get_provider

    adapter = get_adapter("openai")
    provider = get_provider("openai", system_message="...")

To add a new provider:
    from web.llm.registry import register
    register("my_provider", factory=my_factory, env_prefix="MY_PROVIDER_")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .base import LLMAdapter
from .provider import AssistantLLMProvider, build_agent_provider


# ---------------------------------------------------------------------------
# Provider spec
# ---------------------------------------------------------------------------

@dataclass
class ProviderSpec:
    """Registration entry for a single provider."""
    name: str
    factory: Callable[..., LLMAdapter]
    env_prefix: str = ""
    default_model: str = ""
    required_env_keys: List[str] = field(default_factory=list)
    optional_env_keys: List[str] = field(default_factory=list)
    description: str = ""


# Global registry
_registry: Dict[str, ProviderSpec] = {}


def register(spec: ProviderSpec) -> None:
    """Register a provider spec."""
    _registry[spec.name] = spec


def get_spec(name: str) -> ProviderSpec:
    if name not in _registry:
        available = ", ".join(sorted(_registry)) or "(none)"
        raise ValueError(f"Unknown provider: {name!r}. Available: {available}")
    return _registry[name]


def list_providers() -> List[Dict[str, Any]]:
    """Return a list of registered provider summaries."""
    result = []
    for name, spec in sorted(_registry.items()):
        env_keys = spec.required_env_keys + spec.optional_env_keys
        result.append({
            "name": name,
            "description": spec.description,
            "default_model": spec.default_model,
            "env_keys": env_keys,
        })
    return result


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _read_env(spec: ProviderSpec, *, model_override: str | None = None) -> dict:
    """Read environment variables for a provider and return a config dict."""
    prefix = spec.env_prefix
    cfg: dict = {}

    # Required keys
    for key in spec.required_env_keys:
        val = os.getenv(f"{prefix}{key}")
        if not val:
            raise RuntimeError(
                f"Environment variable {prefix}{key} is not set "
                f"(required for provider '{spec.name}')"
            )
        cfg[key.lower()] = val

    # Optional keys
    for key in spec.optional_env_keys:
        cfg[key.lower()] = os.getenv(f"{prefix}{key}") or None

    # Model: override > env > default
    cfg["model"] = (
        model_override
        or os.getenv(f"{prefix}MODEL")
        or spec.default_model
    )

    return cfg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_adapter(
    name: str,
    *,
    model: str | None = None,
) -> LLMAdapter:
    """Build an adapter instance for the given provider name."""
    spec = get_spec(name)
    cfg = _read_env(spec, model_override=model)
    return spec.factory(cfg)


def get_provider(
    name: str,
    *,
    model: str | None = None,
    system_message: str | None = None,
) -> AssistantLLMProvider:
    """Build an agent-ready provider for the given provider name."""
    adapter = get_adapter(name, model=model)
    return build_agent_provider(adapter, system_message=system_message)


def get_default_provider_name() -> str:
    """Return the default provider name from env or 'openai'."""
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def get_default_system_message() -> str:
    """Return the default system message from env."""
    return os.getenv(
        "SYSTEM_MESSAGE",
        "你叫coco，根据用户给的消息，帮助用户解决问题，语气要温和。",
    )


# ---------------------------------------------------------------------------
# Built-in factories
# ---------------------------------------------------------------------------

def _openai_factory(cfg: dict) -> LLMAdapter:
    from .openai_adapter import OpenAIAdapter

    return OpenAIAdapter(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url"),
    )


def _deepseek_factory(cfg: dict) -> LLMAdapter:
    from .deepseek_adapter import DeepseekAdapter

    return DeepseekAdapter(
        model=cfg["model"],
        api_key=cfg["api_key"],
        base_url=cfg.get("base_url"),
    )


def _ollama_factory(cfg: dict) -> LLMAdapter:
    from .ollama_adapter import OllamaAdapter

    return OllamaAdapter(
        model=cfg["model"],
        base_url=cfg.get("base_url"),
    )


def _dummy_factory(cfg: dict) -> LLMAdapter:
    from .dummy_adapter import DummyAdapter

    return DummyAdapter()


# ---------------------------------------------------------------------------
# Register built-in providers
# ---------------------------------------------------------------------------

register(ProviderSpec(
    name="openai",
    factory=_openai_factory,
    env_prefix="OPENAI_",
    default_model="gpt-4o-mini",
    required_env_keys=["API_KEY"],
    optional_env_keys=["BASE_URL"],
    description="OpenAI GPT models (default)",
))

register(ProviderSpec(
    name="deepseek",
    factory=_deepseek_factory,
    env_prefix="DEEPSEEK_",
    default_model="deepseek-chat",
    required_env_keys=["API_KEY"],
    optional_env_keys=["BASE_URL"],
    description="Deepseek models (OpenAI-compatible)",
))

register(ProviderSpec(
    name="ollama",
    factory=_ollama_factory,
    env_prefix="OLLAMA_",
    default_model="qwen2.5:7b",
    required_env_keys=[],
    optional_env_keys=["BASE_URL"],
    description="Local Ollama models",
))

register(ProviderSpec(
    name="dummy",
    factory=_dummy_factory,
    env_prefix="",
    default_model="dummy",
    required_env_keys=[],
    optional_env_keys=[],
    description="Dummy adapter for testing (no API key needed)",
))
