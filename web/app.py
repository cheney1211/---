"""聊天 Web 界面的 FastAPI 应用。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router as chat_router
from storage import init_db, recover_pending_tool_calls, get_engine

# 从项目根目录加载 .env 文件
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

logger = logging.getLogger("web.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭生命周期管理。"""
    # ---- 启动 ----
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    await init_db()
    recovered = await recover_pending_tool_calls()
    if recovered:
        logger.warning(
            "已恢复 %d 个待处理的工具调用 -> 标记为错误（需要手动重试）",
            len(recovered),
        )

    # 确保工作空间根目录存在
    (_ROOT / "workSpace").mkdir(exist_ok=True)

    logger.info("数据库已就绪")
    yield
    # ---- 关闭 ----
    from web.llm.langgraph_provider import LangGraphProvider
    await LangGraphProvider.close_all()
    engine = get_engine()
    await engine.dispose()
    logger.info("关闭完成")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(title="xiaozhushou", version="0.3.0", lifespan=lifespan)

    # CORS：允许 Next.js 开发服务器和常见本地端口
    # 使用宽松设置以避免预检请求失败，适用于本地开发。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    app.include_router(chat_router, prefix="/api")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # 排除工作空间和数据目录，使重载监视器不监视这些目录
    # 仅监视项目根目录下的 .py 文件（不包括子目录）。
    # 这样可以防止 LLM 工具在用户项目中写入文件时导致 SSE 中断。
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_includes=["*.py"],
        reload_excludes=["workSpace/*", "data/*", "frontend/*", ".venv/*", ".next/*", "storage/*.db"],
    )
