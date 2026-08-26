"""Skill and tool routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from assistant.tools import list_tools as list_all_tools
from assistant.skills import list_skills, get_skill_details, reload_skills

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
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
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tools")
async def tools():
    """List all registered tools."""
    return {"tools": list_all_tools()}


@router.get("/skills", response_model=List[SkillSummary])
async def skills():
    """List all registered skills."""
    return list_skills()


@router.get("/skills/{skill_name}", response_model=SkillDetail)
async def skill_detail(skill_name: str):
    """Return details for a given skill, including tool metadata."""
    try:
        detail = get_skill_details(skill_name)
    except ValueError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    return detail


@router.post("/skills/reload")
async def skills_reload():
    """Reload all skills from disk."""
    count = reload_skills()
    return {"status": "ok", "skill_count": count}
