"""记忆管理路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from storage.memory import (
    read_memory,
    write_memory,
    read_global_memory,
    write_global_memory,
    init_memory,
)
from storage.repositories import ProjectRepo
from assistant.tools.workspace import get_workspace_root

router = APIRouter()


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class MemoryContent(BaseModel):
    content: str


class MemoryResponse(BaseModel):
    content: str | None
    path: str


# ---------------------------------------------------------------------------
# 项目记忆端点
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/memory", response_model=MemoryResponse)
async def get_project_memory(project_id: str):
    """获取项目的记忆内容。"""
    project = await ProjectRepo.get(project_id)
    if not project:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})

    if not project.root_path:
        return JSONResponse(status_code=400, content={"error": "项目未设置根目录路径"})

    project_root = Path(project.root_path)
    init_memory(project_root)  # 确保记忆文件存在
    content = read_memory(project_root)
    memory_path = str(project_root / ".agent" / "memory.md")

    return MemoryResponse(content=content, path=memory_path)


@router.put("/projects/{project_id}/memory")
async def update_project_memory(project_id: str, request: MemoryContent):
    """更新项目的记忆内容。"""
    project = await ProjectRepo.get(project_id)
    if not project:
        return JSONResponse(status_code=404, content={"error": "项目不存在"})

    if not project.root_path:
        return JSONResponse(status_code=400, content={"error": "项目未设置根目录路径"})

    project_root = Path(project.root_path)
    success = write_memory(project_root, request.content)

    if not success:
        return JSONResponse(status_code=500, content={"error": "写入记忆文件失败"})

    return {"ok": True, "path": str(project_root / ".agent" / "memory.md")}


# ---------------------------------------------------------------------------
# 全局记忆端点
# ---------------------------------------------------------------------------


@router.get("/memory/global", response_model=MemoryResponse)
async def get_global_memory():
    """获取全局记忆内容。"""
    workspace = get_workspace_root()
    content = read_global_memory(workspace)
    memory_path = str(workspace / ".agent" / "memory.md")

    return MemoryResponse(content=content, path=memory_path)


@router.put("/memory/global")
async def update_global_memory(request: MemoryContent):
    """更新全局记忆内容。"""
    workspace = get_workspace_root()
    success = write_global_memory(workspace, request.content)

    if not success:
        return JSONResponse(status_code=500, content={"error": "写入全局记忆文件失败"})

    return {"ok": True, "path": str(workspace / ".agent" / "memory.md")}
