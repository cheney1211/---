"""Project management routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from storage.repositories import ProjectRepo, SessionRepo
from assistant.tools.workspace import ensure_project_dir

router = APIRouter()

_DEFAULT_NAMES = ["默认项目"]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: str | None
    updated_at: str | None


class CreateProjectRequest(BaseModel):
    name: str | None = None


class RenameProjectRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=List[ProjectOut])
async def list_projects():
    """Return all projects ordered by creation time."""
    rows = await ProjectRepo.list_all()
    return [
        ProjectOut(
            id=r.id,
            name=r.name,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


@router.post("/projects", response_model=ProjectOut)
async def create_project(request: CreateProjectRequest):
    """Create a new project with an optional display name."""
    name = (request.name or "").strip()
    if not name:
        name = await _generate_default_name()

    project_id = str(uuid.uuid4())
    row = await ProjectRepo.create(project_id, name)
    ensure_project_dir(project_id)

    return ProjectOut(
        id=row.id,
        name=row.name,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def rename_project(project_id: str, request: RenameProjectRequest):
    """Rename a project (display name only, does not affect filesystem)."""
    ok = await ProjectRepo.rename(project_id, request.name.strip())
    if not ok:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    row = await ProjectRepo.get(project_id)
    return ProjectOut(
        id=row.id,
        name=row.name,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and all its sessions."""
    ok = await ProjectRepo.delete(project_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    return {"deleted": True, "project_id": project_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _generate_default_name() -> str:
    """Generate a unique default project name like '未命名项目', '未命名项目-2', ..."""
    existing = await ProjectRepo.list_all()
    existing_names = {p.name for p in existing}

    base = "未命名项目"
    if base not in existing_names:
        return base
    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if candidate not in existing_names:
            return candidate
    return f"{base}-{int(datetime.now(timezone.utc).timestamp())}"
