"""模型管理路由 — Provider CRUD + 模型列表自动获取。"""

from __future__ import annotations

import asyncio
import json as _json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from web.config import (
    get_providers, add_provider, update_provider, delete_provider,
    get_active_model, set_active_model, mask_api_key,
)

logger = logging.getLogger("models_routes")
router = APIRouter()


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------

@router.get("/providers/list")
async def list_all_providers():
    """返回所有已配置的 Provider（API key 脱敏）。"""
    providers = get_providers()
    active_provider, active_model = get_active_model()
    return {
        "providers": [
            {
                "id": p["id"],
                "name": p["name"],
                "base_url": p.get("base_url", ""),
                "api_key_masked": mask_api_key(p.get("api_key", "")),
                "api_key_set": bool(p.get("api_key")),
                "api_format": p.get("api_format", "openai"),
                "models": [
                    {
                        "id": m["id"],
                        "display_name": m.get("display_name", m["id"]),
                        "context_window": m.get("context_window", 0),
                        "max_output_tokens": m.get("max_output_tokens", 0),
                    }
                    for m in p.get("models", [])
                ],
                "is_active": p.get("id") == (active_provider or {}).get("id"),
            }
            for p in providers
        ],
        "active_provider_id": (active_provider or {}).get("id"),
        "active_model_id": (active_model or {}).get("id"),
    }


class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str
    api_format: str = "openai"  # openai | anthropic | ollama


@router.post("/providers")
async def create_provider(body: ProviderCreate):
    """添加新 Provider。"""
    provider = add_provider({
        "name": body.name,
        "base_url": body.base_url,
        "api_key": body.api_key,
        "api_format": body.api_format,
        "models": [],
    })
    return {"status": "ok", "provider_id": provider["id"]}


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_format: str | None = None


@router.put("/providers/{provider_id}")
async def update_provider_api(provider_id: str, body: ProviderUpdate):
    """更新 Provider 配置。"""
    updates = body.model_dump(exclude_none=True)
    result = update_provider(provider_id, updates)
    if not result:
        return {"status": "error", "message": "Provider not found"}
    return {"status": "ok"}


@router.delete("/providers/{provider_id}")
async def delete_provider_api(provider_id: str):
    """删除 Provider。"""
    ok = delete_provider(provider_id)
    return {"status": "ok" if ok else "error"}


@router.post("/providers/{provider_id}/set-active")
async def set_provider_active(provider_id: str):
    """设置 Provider 为活跃（如果没有模型则无模型激活）。"""
    providers = get_providers()
    for p in providers:
        if p.get("id") == provider_id:
            if p.get("models"):
                set_active_model(provider_id, p["models"][0]["id"])
            else:
                set_active_model(provider_id, "")
            return {"status": "ok"}
    return {"status": "error"}


# ---------------------------------------------------------------------------
# 模型自动获取
# ---------------------------------------------------------------------------

class FetchModelsRequest(BaseModel):
    base_url: str
    api_key: str
    api_format: str = "openai"


async def _fetch_openai_models(base_url: str, api_key: str) -> list[dict]:
    """OpenAI 兼容格式: GET {base_url}/models"""
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 401:
            raise ValueError("API Key 无效或已过期")
        if resp.status_code == 403:
            raise ValueError("API Key 没有访问模型列表的权限")
        resp.raise_for_status()
        raw = resp.text.strip()
        if not raw:
            raise ValueError(f"API 返回空响应，请检查 Base URL 是否正确: {url}")
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError:
            raise ValueError(f"API 返回非 JSON 内容: {raw[:200]}")
        logger.info("[fetch-openai] URL=%s, 响应 keys: %s", url, list(data.keys()) if isinstance(data, dict) else "array")
        # 兼容多种响应格式
        raw_list = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            raw_list = data.get("data") or data.get("models") or data.get("items") or []
        models = []
        for item in raw_list:
            if isinstance(item, str):
                model_id = item
            else:
                model_id = item.get("id") or item.get("name") or item.get("model") or ""
            if model_id:
                models.append({
                    "id": model_id,
                    "display_name": item.get("display_name", model_id) if isinstance(item, dict) else model_id,
                    "context_window": item.get("context_window", 0) if isinstance(item, dict) else 0,
                    "max_output_tokens": item.get("max_output_tokens", 0) if isinstance(item, dict) else 0,
                })
        return models


async def _fetch_anthropic_models(base_url: str, api_key: str) -> list[dict]:
    """Anthropic 格式: GET {base_url}/models"""
    url = f"{base_url.rstrip('/')}/models"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 401:
            raise ValueError("API Key 无效或已过期")
        resp.raise_for_status()
        raw = resp.text.strip()
        if not raw:
            raise ValueError(f"API 返回空响应，请检查 Base URL 是否正确: {url}")
        data = _json.loads(raw)
        models = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            models.append({
                "id": model_id,
                "display_name": item.get("display_name", model_id),
                "context_window": item.get("max_input_tokens", 0),
                "max_output_tokens": item.get("max_output_tokens", 0),
            })
        return models


async def _fetch_ollama_models(base_url: str) -> list[dict]:
    """Ollama 格式: GET {base_url}/api/tags"""
    url = f"{base_url.rstrip('/')}/api/tags"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        raw = resp.text.strip()
        if not raw:
            raise ValueError(f"Ollama 返回空响应，请检查是否已启动: {url}")
        data = _json.loads(raw)
        models = []
        for item in data.get("models", []):
            model_id = item.get("name", "")
            models.append({
                "id": model_id,
                "display_name": model_id,
                "context_window": 0,
                "max_output_tokens": 0,
            })
        return models


@router.post("/providers/fetch-models")
async def fetch_models(body: FetchModelsRequest):
    """从 Provider 端点自动获取可用模型列表。"""
    try:
        if body.api_format == "anthropic":
            models = await _fetch_anthropic_models(body.base_url, body.api_key)
        elif body.api_format == "ollama":
            models = await _fetch_ollama_models(body.base_url)
        else:
            models = await _fetch_openai_models(body.base_url, body.api_key)
        logger.info("[fetch-models] 获取到 %d 个模型 (format=%s)", len(models), body.api_format)
        return {"status": "ok", "models": models}
    except httpx.TimeoutException:
        return {"status": "error", "message": "连接超时，请检查 Base URL 是否正确"}
    except httpx.ConnectError:
        return {"status": "error", "message": "无法连接，请检查 Base URL 是否正确"}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except _json.JSONDecodeError as e:
        return {"status": "error", "message": f"API 返回非 JSON 内容: {str(e)[:100]}"}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "message": f"请求失败 ({e.response.status_code}): {e.response.text[:200]}"}
    except Exception as e:
        logger.exception("[fetch-models] 未知错误")
        return {"status": "error", "message": f"获取失败: {str(e)}"}


# ---------------------------------------------------------------------------
# Provider 内模型管理
# ---------------------------------------------------------------------------

class ModelAdd(BaseModel):
    id: str
    display_name: str = ""
    context_window: int = 0
    max_output_tokens: int = 0


@router.post("/providers/{provider_id}/models")
async def add_model(provider_id: str, body: ModelAdd):
    """向 Provider 添加一个模型。"""
    providers = get_providers()
    for p in providers:
        if p.get("id") == provider_id:
            # 去重
            existing_ids = {m["id"] for m in p.get("models", [])}
            if body.id in existing_ids:
                return {"status": "error", "message": "模型已存在"}
            model = {
                "id": body.id,
                "display_name": body.display_name or body.id,
                "context_window": body.context_window,
                "max_output_tokens": body.max_output_tokens,
            }
            p.setdefault("models", []).append(model)
            from web.config import save_config, load_config
            cfg = load_config()
            cfg["providers"] = providers
            save_config(cfg)
            return {"status": "ok", "model": model}
    return {"status": "error", "message": "Provider not found"}


@router.delete("/providers/{provider_id}/models/{model_id}")
async def remove_model(provider_id: str, model_id: str):
    """从 Provider 删除一个模型。"""
    from web.config import save_config, load_config
    providers = get_providers()
    for p in providers:
        if p.get("id") == provider_id:
            before = len(p.get("models", []))
            p["models"] = [m for m in p.get("models", []) if m["id"] != model_id]
            if len(p["models"]) < before:
                cfg = load_config()
                cfg["providers"] = providers
                save_config(cfg)
                return {"status": "ok"}
            return {"status": "error", "message": "模型不存在"}
    return {"status": "error", "message": "Provider not found"}


@router.post("/providers/{provider_id}/models/{model_id}/set-active")
async def set_model_active(provider_id: str, model_id: str):
    """设置指定模型为当前活跃模型。"""
    set_active_model(provider_id, model_id)
    return {"status": "ok"}
