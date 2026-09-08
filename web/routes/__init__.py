"""路由包 — 将所有子路由组装为一个。"""

from fastapi import APIRouter

from .system import router as system_router
from .projects import router as projects_router
from .sessions import router as sessions_router
from .skills import router as skills_router
from .chat import router as chat_router
from .memory import router as memory_router
from .context import router as context_router
from .models import router as models_router

router = APIRouter()
router.include_router(system_router)
router.include_router(projects_router)
router.include_router(sessions_router)
router.include_router(skills_router)
router.include_router(chat_router)
router.include_router(memory_router)
router.include_router(context_router)
router.include_router(models_router)
