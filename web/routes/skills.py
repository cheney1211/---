"""技能和工具路由。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from assistant.tools import list_tools as list_all_tools
from assistant.skills import list_skills, get_skill_details, reload_skills

router = APIRouter()


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------

class SkillSummary(BaseModel):
    name: str
    description: str
    tags: List[str]
    tool_names: List[str]
    version: str
    author: str


class SkillToolOut(BaseModel):
    name: str
    description: str


class SkillDetail(BaseModel):
    name: str
    description: str
    tags: List[str]
    tool_names: List[str]
    instruction: str | None = None
    version: str
    author: str
    tools: List[SkillToolOut]


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/tools")
async def tools():
    """列出所有已注册的工具。"""
    return {"tools": list_all_tools()}


@router.get("/skills", response_model=List[SkillSummary])
async def skills():
    """列出所有已注册的技能。"""
    return list_skills()


@router.get("/skills/{skill_name}", response_model=SkillDetail)
async def skill_detail(skill_name: str):
    """返回指定技能的详细信息，包括工具元数据。"""
    try:
        detail = get_skill_details(skill_name)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    return detail


@router.post("/skills/reload")
async def skills_reload():
    """从磁盘重新加载所有技能。"""
    count = reload_skills()
    return {"status": "ok", "skill_count": count}
