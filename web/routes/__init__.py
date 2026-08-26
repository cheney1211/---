"""Routes package — assembles all sub-routers into one."""

from fastapi import APIRouter

from .system import router as system_router
from .sessions import router as sessions_router
from .skills import router as skills_router
from .chat import router as chat_router

router = APIRouter()
router.include_router(system_router)
router.include_router(sessions_router)
router.include_router(skills_router)
router.include_router(chat_router)
