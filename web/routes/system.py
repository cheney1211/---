"""System routes: health check and provider listing."""

from __future__ import annotations

from fastapi import APIRouter

from web.llm import get_default_provider_name, list_providers

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/providers")
async def providers():
    """List all registered LLM providers."""
    return {
        "default": get_default_provider_name(),
        "providers": list_providers(),
    }
