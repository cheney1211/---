"""聊天服务 — 协调会话、消息和提供者逻辑。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import AsyncIterable

from assistant.core import AgentMessage, AgentState
from assistant.tools import get_tools, register as register_tool
from assistant.tools.builtin.call_skill import CallSkillTool, configure as configure_call_skill
from assistant.skills import build_skills_system_prompt
from storage.repositories import SessionRepo, MessageRepo, PendingToolRepo, ProjectRepo
from storage.memory import read_memory, read_global_memory, init_memory
from assistant.tools.workspace import get_workspace_root, get_platform_hint, project_context
from web.llm import get_adapter, get_provider, get_default_provider_name, get_default_system_message
from web.utils.message_utils import classify_and_extract


async def _resolve_project_root(project_id: str | None) -> str | None:
    """从数据库返回项目的 root_path，如果不存在则返回 None。"""
    if not project_id:
        return None
    project = await ProjectRepo.get(project_id)
    return project.root_path if project and project.root_path else None


async def get_or_create_session(
    session_id: str | None = None,
    *,
    project_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, AgentState]:
    """返回由数据库支持的 (session_id, AgentState)。"""
    sid = session_id or str(uuid.uuid4())
    await SessionRepo.get_or_create(sid, project_id=project_id, provider=provider, model=model)
    messages = await MessageRepo.list_recent(sid)
    turns = await MessageRepo.get_turns(sid)
    state = AgentState(messages=messages, turns=turns)
    return sid, state


def resolve_provider(
    *,
    project_id: str | None = None,
    root_path: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    mode: str = "confirm",
):
    """构建带有工具（包括 call_skill）和技能索引的提供者。"""
    provider_name = provider or get_default_provider_name()
    base_system = get_default_system_message()
    skill_index = build_skills_system_prompt()
    system_message = f"{base_system}\n\n{skill_index}" if skill_index else base_system

    # 注入工作区和平台上下文
    workspace = get_workspace_root()
    if root_path:
        workspace_hint = (
            f"\n\n工作区信息:\n"
            f"- 项目根目录: {workspace}\n"
            f"- 这是用户项目的实际目录，所有文件查找、代码修改、脚本运行等操作都以此目录为根目录。\n"
            f"- {get_platform_hint()}\n"
            f"- 文件读写限制在项目根目录内，读取项目外的文件需要用户确认。\n"
            f"- 路径安全：禁止使用 ../ 等方式跳出项目根目录，禁止指向项目外的符号链接。"
            f"所有文件路径必须在项目根目录以内。"
        )
    else:
        workspace_hint = (
            f"\n\n工作区信息:\n"
            f"- 工作区目录: {workspace}\n"
            f"- {get_platform_hint()}\n"
            f"- 文件读写限制在工作区内，读取工作区外的文件需要用户确认。"
        )
    system_message += workspace_hint

    # 如果提供了 project_id，则注入项目记忆
    if project_id:
        project_memory = _load_project_memory(root_path)
        if project_memory:
            system_message += f"\n\n## 项目记忆\n{project_memory}"
    else:
        # 为非项目会话加载全局记忆
        global_memory = read_global_memory(workspace)
        if global_memory:
            system_message += f"\n\n## 全局记忆\n{global_memory}"

    adapter = get_adapter(provider_name, model=model)
    configure_call_skill(adapter.llm, base_system)
    register_tool(CallSkillTool())

    tools = get_tools()
    return get_provider(provider_name, model=model, system_message=system_message, tools=tools, confirmation_mode=mode)


def _load_project_memory(root_path: str | None) -> str | None:
    """从项目的 root_path 加载记忆内容。"""
    if not root_path:
        return None
    try:
        project_root = Path(root_path)
        init_memory(project_root)  # 确保记忆文件存在
        return read_memory(project_root)
    except Exception:
        return None


async def persist_message(session_id: str, msg: AgentMessage, *, kind: str = "user") -> None:
    """写入一条消息并跟踪待处理的工具调用。"""
    await MessageRepo.append(session_id, msg, kind=kind)

    if kind == "tool_request" and msg.metadata.get("tool_calls"):
        for tc in msg.metadata["tool_calls"]:
            await PendingToolRepo.create(
                session_id=session_id,
                message_id=0,
                call_id=tc.get("id", ""),
                tool_name=tc["name"],
                arguments=tc.get("args", {}),
            )

    if kind == "tool_result":
        tcid = msg.metadata.get("tool_call_id", "")
        if tcid:
            pendings = await PendingToolRepo.list_resumable(session_id)
            for p in pendings:
                if p.call_id == tcid and p.status in ("queued", "running"):
                    await PendingToolRepo.mark_done(p.id)


async def process_message(
    session_id: str,
    state: AgentState,
    user_text: str,
    *,
    project_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    mode: str = "confirm",
) -> str:
    """非流式处理：持久化用户消息，运行提供者，持久化所有响应，返回回复。"""
    user_msg = AgentMessage(role="user", content=user_text)
    await persist_message(session_id, user_msg, kind="user")
    state.append(user_msg)

    root_path = await _resolve_project_root(project_id)
    with project_context(project_id, root_path=root_path):
        llm_provider = resolve_provider(
            project_id=project_id, root_path=root_path,
            provider=provider, model=model, mode=mode,
        )

        full_text = ""
        async for msg in llm_provider(state, session_id=session_id):
            if msg.metadata.get("chunk"):
                continue
            kind, is_chunk = classify_and_extract(msg)
            await persist_message(session_id, msg, kind=kind)
            state.append(msg)
            if msg.role == "assistant":
                full_text = msg.content

    state.turns += 1
    await SessionRepo.set_turns(session_id, state.turns)
    return full_text


async def process_message_stream(
    session_id: str,
    state: AgentState,
    user_text: str,
    *,
    project_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    mode: str = "confirm",
) -> AsyncIterable[dict]:
    """流式处理：生成 SSE 事件字典（session / status / chunk / done）。"""
    user_msg = AgentMessage(role="user", content=user_text)
    await persist_message(session_id, user_msg, kind="user")
    state.append(user_msg)

    root_path = await _resolve_project_root(project_id)
    with project_context(project_id, root_path=root_path):
        llm_provider = resolve_provider(
            project_id=project_id, root_path=root_path,
            provider=provider, model=model, mode=mode,
        )

        yield {"event": "session", "data": {"session_id": session_id}}

        full_text = ""
        async for msg in llm_provider(state, session_id=session_id):
            status_data = msg.metadata.get("status")
            if status_data:
                yield {"event": "status", "data": status_data}
                continue

            if msg.metadata.get("chunk"):
                full_text += msg.content
                yield {"event": "chunk", "data": {"content": msg.content}}
                continue

            kind, is_chunk = classify_and_extract(msg)
            await persist_message(session_id, msg, kind=kind)
            state.append(msg)
            if msg.role == "assistant":
                full_text = msg.content

    state.turns += 1
    await SessionRepo.set_turns(session_id, state.turns)
    yield {"event": "done", "data": {"content": full_text, "session_id": session_id}}
