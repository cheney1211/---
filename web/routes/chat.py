"""聊天和确认路由。"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from web.llm.langgraph_provider import confirmation_manager
from web.services.chat_service import get_or_create_session, process_message, process_message_stream

router = APIRouter()


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    project_id: str | None = None
    provider: str | None = None
    model: str | None = None
    mode: str = "confirm"


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class ConfirmRequest(BaseModel):
    approved: bool
    allow_always: Optional[bool] = None


# ---------------------------------------------------------------------------
# 聊天端点
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """非流式 REST 端点。"""
    session_id, state = await get_or_create_session(
        request.session_id, project_id=request.project_id,
        provider=request.provider, model=request.model,
    )
    reply = await process_message(
        session_id, state, request.message,
        project_id=request.project_id,
        provider=request.provider, model=request.model, mode=request.mode,
    )
    return ChatResponse(reply=reply, session_id=session_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式端点。"""
    session_id, state = await get_or_create_session(
        request.session_id, project_id=request.project_id,
        provider=request.provider, model=request.model,
    )

    async def event_generator():
        try:
            async for event in process_message_stream(
                session_id, state, request.message,
                project_id=request.project_id,
                provider=request.provider, model=request.model, mode=request.mode,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }
        except Exception as e:
            import traceback
            print(f"[SSE Error] {e}")
            traceback.print_exc()
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# 确认端点
# ---------------------------------------------------------------------------

@router.post("/confirm/{confirmation_id}")
async def confirm_tool(confirmation_id: str, request: ConfirmRequest):
    """批准或拒绝待处理的工具确认请求。"""
    found = confirmation_manager.resolve(confirmation_id, request.approved)
    if not found:
        return JSONResponse(
            status_code=404,
            content={"error": f"Confirmation request '{confirmation_id}' not found or already resolved"},
        )
    return {
        "status": "resolved",
        "confirmation_id": confirmation_id,
        "approved": request.approved,
    }


@router.get("/confirm/pending")
async def list_pending_confirmations():
    """列出所有待处理的确认请求。"""
    return {"pending": confirmation_manager.list_pending()}
