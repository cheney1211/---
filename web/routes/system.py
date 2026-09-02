"""System routes: health check, provider listing, and workspace management."""

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
    """List all registered LLM providers."""
    return {
        "default": get_default_provider_name(),
        "providers": list_providers(),
    }


# ---------------------------------------------------------------------------
# Workspace management
# ---------------------------------------------------------------------------

class WorkspaceUpdate(BaseModel):
    path: str


def _search_roots() -> list[Path]:
    """Return common root directories to search for folder names."""
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
    """Find all directories matching *name* under common search roots."""
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
    """Return the current workspace folder name."""
    root = get_workspace_root()
    return {"workspace_root": root.name}


@router.get("/workspace/search")
async def search_workspace(name: str):
    """Search for directories matching *name* across common locations.

    Returns a list of absolute paths. The frontend can use this to let the
    user pick the correct one when showDirectoryPicker only gives a folder name.
    """
    name = name.strip()
    if not name:
        return {"matches": []}
    return {"matches": _find_matches(name)}


@router.put("/workspace")
async def update_workspace(request: WorkspaceUpdate):
    """Update the workspace root directory.

    Accepts either an absolute path or a folder name.
    If a folder name matches multiple locations, returns them for the user to choose.
    """
    raw = request.path.strip()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "路径不能为空"})

    # Absolute path that exists → use directly
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.is_dir():
        new_root = set_workspace_root(raw)
        return {"workspace_root": new_root.name}

    # Folder name → search for matches
    matches = _find_matches(raw)
    if len(matches) == 1:
        new_root = set_workspace_root(matches[0])
        return {"workspace_root": new_root.name}
    if len(matches) > 1:
        return JSONResponse(status_code=200, content={"workspace_root": "", "matches": matches})

    return JSONResponse(status_code=400, content={"error": f"未找到目录: {raw}"})
