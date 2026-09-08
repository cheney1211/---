"""运行时配置持久化模块。

配置优先级：
1. data/config.json（用户通过 UI 设置，运行时持久化）
2. .env 环境变量（初始默认值，config.json 未配置时使用）
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("config")

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "data" / "config.json"

_cache: dict[str, Any] = {}
_loaded = False


def _ensure_data_dir() -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    global _cache, _loaded
    if _loaded:
        return _cache
    try:
        if _CONFIG_PATH.exists():
            _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        else:
            _cache = {}
    except Exception as e:
        logger.warning("加载配置失败: %s", e)
        _cache = {}
    _loaded = True
    return _cache


def save_config(config: dict[str, Any]) -> None:
    global _cache
    _ensure_data_dir()
    _CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _cache = config


# ---------------------------------------------------------------------------
# 多 Provider 配置管理
# ---------------------------------------------------------------------------

def get_providers() -> list[dict]:
    """返回所有已配置的 Provider 列表。"""
    cfg = load_config()
    return cfg.get("providers", [])


def save_providers(providers: list[dict]) -> None:
    """保存 Provider 列表。"""
    cfg = load_config()
    cfg["providers"] = providers
    save_config(cfg)


def add_provider(provider: dict) -> dict:
    """添加新 Provider，生成 ID，保存。"""
    cfg = load_config()
    providers = cfg.get("providers", [])
    import uuid
    provider["id"] = str(uuid.uuid4())[:8]
    providers.append(provider)
    cfg["providers"] = providers
    save_config(cfg)
    return provider


def update_provider(provider_id: str, updates: dict) -> dict | None:
    """更新指定 Provider 的字段。"""
    cfg = load_config()
    providers = cfg.get("providers", [])
    for p in providers:
        if p.get("id") == provider_id:
            p.update(updates)
            cfg["providers"] = providers
            save_config(cfg)
            return p
    return None


def delete_provider(provider_id: str) -> bool:
    """删除指定 Provider。"""
    cfg = load_config()
    providers = cfg.get("providers", [])
    before = len(providers)
    providers = [p for p in providers if p.get("id") != provider_id]
    if len(providers) < before:
        cfg["providers"] = providers
        save_config(cfg)
        return True
    return False


def get_active_provider() -> dict | None:
    """获取当前活跃的 Provider（第一个有模型的）。"""
    providers = get_providers()
    for p in providers:
        if p.get("models"):
            return p
    return providers[0] if providers else None


def get_active_model() -> tuple[dict | None, dict | None]:
    """获取当前活跃的 Provider 和 Model。返回 (provider, model)。"""
    cfg = load_config()
    active_id = cfg.get("active_provider_id")
    active_model_id = cfg.get("active_model_id")

    providers = get_providers()
    for p in providers:
        if p.get("id") == active_id:
            for m in p.get("models", []):
                if m.get("id") == active_model_id:
                    return p, m
            if p.get("models"):
                return p, p["models"][0]
            return p, None
    if providers:
        p = providers[0]
        if p.get("models"):
            return p, p["models"][0]
        return p, None
    return None, None


def set_active_model(provider_id: str, model_id: str) -> None:
    """设置当前活跃的 Provider 和 Model。"""
    cfg = load_config()
    cfg["active_provider_id"] = provider_id
    cfg["active_model_id"] = model_id
    save_config(cfg)


# ---------------------------------------------------------------------------
# 兼容旧接口：get_llm_config / save_llm_config
# ---------------------------------------------------------------------------

def get_llm_config() -> dict[str, str]:
    """返回当前生效的 LLM 配置（兼容旧接口，用于 registry）。"""
    provider, model = get_active_model()
    if provider and model:
        return {
            "provider": provider.get("api_format", "openai"),
            "provider_name": provider.get("name", ""),
            "api_key": provider.get("api_key", ""),
            "model": model.get("id", ""),
            "base_url": provider.get("base_url", ""),
        }
    # 回退到环境变量
    env_provider = os.environ.get("LLM_PROVIDER", "openai")
    prefix = env_provider.upper()
    return {
        "provider": env_provider,
        "provider_name": env_provider,
        "api_key": os.environ.get(f"{prefix}_API_KEY", ""),
        "model": os.environ.get(f"{prefix}_MODEL", ""),
        "base_url": os.environ.get(f"{prefix}_BASE_URL", ""),
    }


def mask_api_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "****" if key else ""
    return f"{key[:4]}...{key[-4:]}"
