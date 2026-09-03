"""系统路由：健康检查、提供者列表和工作空间管理。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from assistant.tools.workspace import get_workspace_root, set_workspace_root
from web.llm import get_default_provider_name, list_providers

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/providers")
async def providers():
    """列出所有已注册的 LLM 提供者。"""
    return {
        "default": get_default_provider_name(),
        "providers": list_providers(),
    }


# ---------------------------------------------------------------------------
# 工作空间管理
# ---------------------------------------------------------------------------

class WorkspaceUpdate(BaseModel):
    path: str


def _search_roots() -> list[Path]:
    """返回用于搜索文件夹名称的常见根目录列表。"""
    roots: list[Path] = [get_workspace_root(), get_workspace_root().parent, Path.home()]
    if os.name == "nt":
        for drive in "CDEFG":
            p = Path(f"{drive}:\\")
            if p.exists():
                roots.append(p)
    else:
        roots.extend([Path("/"), Path("/home")])
    return roots


def _find_matches(name: str) -> list[str]:
    """在常见搜索根目录下查找匹配 *name* 的所有目录。"""
    seen: set[str] = set()
    matches: list[str] = []
    for root in _search_roots():
        candidate = (root / name).resolve()
        key = str(candidate).lower() if os.name == "nt" else str(candidate)
        if candidate.is_dir() and key not in seen:
            seen.add(key)
            matches.append(str(candidate))
    return matches


@router.get("/workspace")
async def get_workspace():
    """返回当前工作空间文件夹名称。"""
    root = get_workspace_root()
    return {"workspace_root": root.name}


@router.get("/workspace/search")
async def search_workspace(name: str):
    """在常见位置中搜索匹配 *name* 的目录。

    返回绝对路径列表。当前端只能通过 showDirectoryPicker 获取文件夹名称时，
    可以使用此接口让用户选择正确的目录。
    """
    name = name.strip()
    if not name:
        return {"matches": []}
    return {"matches": _find_matches(name)}


@router.put("/workspace")
async def update_workspace(request: WorkspaceUpdate):
    """更新工作空间根目录。

    接受绝对路径或文件夹名称。
    如果文件夹名称匹配多个位置，则返回列表供用户选择。
    """
    raw = request.path.strip()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "路径不能为空"})

    # 绝对路径且存在 -> 直接使用
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.is_dir():
        new_root = set_workspace_root(raw)
        return {"workspace_root": new_root.name}

    # 文件夹名称 -> 搜索匹配项
    matches = _find_matches(raw)
    if len(matches) == 1:
        new_root = set_workspace_root(matches[0])
        return {"workspace_root": new_root.name}
    if len(matches) > 1:
        return JSONResponse(status_code=200, content={"workspace_root": "", "matches": matches})

    return JSONResponse(status_code=400, content={"error": f"未找到目录: {raw}"})
