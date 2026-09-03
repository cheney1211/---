"""项目管理路由。"""

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
# 响应模型
# ---------------------------------------------------------------------------


class ProjectOut(BaseModel):
    id: str
    name: str
    root_path: str | None
    created_at: str | None
    updated_at: str | None


class CreateProjectRequest(BaseModel):
    name: str | None = None
    root_path: str | None = None


class RenameProjectRequest(BaseModel):
    name: str


class SetRootPathRequest(BaseModel):
    root_path: str


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=List[ProjectOut])
async def list_projects():
    """返回所有项目，按创建时间排序。"""
    rows = await ProjectRepo.list_all()
    return [
        ProjectOut(
            id=r.id,
            name=r.name,
            root_path=r.root_path,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


@router.post("/projects", response_model=ProjectOut)
async def create_project(request: CreateProjectRequest):
    """创建新项目，可选显示名称。"""
    name = (request.name or "").strip()
    if not name:
        name = await _generate_default_name()

    project_id = str(uuid.uuid4())
    row = await ProjectRepo.create(project_id, name, root_path=request.root_path)
    ensure_project_dir(project_id)

    return ProjectOut(
        id=row.id,
        name=row.name,
        root_path=row.root_path,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def rename_project(project_id: str, request: RenameProjectRequest):
    """重命名项目（仅修改显示名称，不影响文件系统）。"""
    ok = await ProjectRepo.rename(project_id, request.name.strip())
    if not ok:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    row = await ProjectRepo.get(project_id)
    return ProjectOut(
        id=row.id,
        name=row.name,
        root_path=row.root_path,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.put("/projects/{project_id}/root-path", response_model=ProjectOut)
async def set_project_root_path(project_id: str, request: SetRootPathRequest):
    """设置项目的根目录路径。"""
    ok = await ProjectRepo.set_root_path(project_id, request.root_path)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    row = await ProjectRepo.get(project_id)
    return ProjectOut(
        id=row.id,
        name=row.name,
        root_path=row.root_path,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """删除项目及其所有会话。"""
    ok = await ProjectRepo.delete(project_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})
    return {"deleted": True, "project_id": project_id}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


async def _generate_default_name() -> str:
    """生成唯一的默认项目名称，如 '未命名项目'、'未命名项目-2' 等。"""
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
