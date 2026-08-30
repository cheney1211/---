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


class WorkspaceResolve(BaseModel):
    dir_name: str


@router.get("/workspace")
async def get_workspace():
    """Return the current workspace root directory."""
    root = get_workspace_root()
    return {"workspace_root": str(root)}


@router.put("/workspace")
async def update_workspace(request: WorkspaceUpdate):
    """Update the workspace root directory."""
    try:
        new_root = set_workspace_root(request.path)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return {"workspace_root": str(new_root)}


@router.post("/workspace/resolve")
async def resolve_workspace_dir(request: WorkspaceResolve):
    """Try to resolve a directory name to a full path.

    Searches common locations to help the browser-based directory picker
    reconstruct the full absolute path.
    """
    dir_name = request.dir_name.strip()
    if not dir_name:
        return {"matched": False, "path": ""}

    # If it's already an absolute path that exists, return it directly
    candidate = Path(dir_name)
    if candidate.is_absolute() and candidate.is_dir():
        return {"matched": True, "path": str(candidate.resolve())}

    # Search locations: current workspace root, its parent, user home, common roots
    search_roots = set()
    ws = get_workspace_root()
    search_roots.add(ws)
    search_roots.add(ws.parent)
    search_roots.add(Path.home())
    if os.name == "nt":
        # Windows: search drive roots
        for drive in "CDEFG":
            p = Path(f"{drive}:\\")
            if p.exists():
                search_roots.add(p)
    else:
        search_roots.add(Path("/"))
        search_roots.add(Path("/home"))

    for root in search_roots:
        candidate = root / dir_name
        if candidate.is_dir():
            return {"matched": True, "path": str(candidate.resolve())}

    return {"matched": False, "path": dir_name}
