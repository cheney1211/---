"""基于 LangGraph 的代理提供者，支持人类确认（human-in-the-loop）。

图结构：
    agent -> human_review（中断）-> path_validator -> tools -> agent -> ...
    agent -> path_validator -> tools -> agent -> ...  （无需确认）
    human_review -> agent  （已拒绝，跳过工具执行）
    path_validator -> agent  （路径校验失败，Agent 自纠错）

path_validator 节点在 tools 之前做路径安全校验（归一化 + 边界检查），
无论走免审还是审批通道，所有工具调用都必须经过它。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncIterable, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.types import interrupt, Command

from assistant.core import AgentMessage, AgentState
from assistant.tools.confirmation import ConfirmationManager, ApprovalStore, is_high_risk
from assistant.tools.workspace import validate_path, resolve_path
from .connection_pool import ConnectionPool

logger = logging.getLogger("langgraph_provider")

# 持久化指纹存储 —— 与 LangGraph checkpoint 共用同一个 .db 文件
_ROOT = Path(__file__).resolve().parent.parent.parent
_APPROVAL_DB_PATH = str(_ROOT / "data" / "langgraph_checkpoints.db")
approval_store = ApprovalStore(_APPROVAL_DB_PATH)
confirmation_manager = ConfirmationManager(store=approval_store)


class LangGraphProvider:
    """基于 LangGraph 中断机制实现人类确认的代理提供者。"""

    _instances: List["LangGraphProvider"] = []
    _pool: Optional[ConnectionPool] = None
    _pool_lock = asyncio.Lock()

    def __init__(
        self,
        llm: BaseChatModel,
        *,
        tools: Optional[List[BaseTool]] = None,
        system_message: str | None = None,
        confirmation_mode: str = "confirm",
        workspace_root: str = "",
    ) -> None:
        self._llm = llm
        self._tools = tools or []
        self._system_message = system_message
        self._confirmation_mode = confirmation_mode
        self._workspace_root = workspace_root
        self._tool_map: Dict[str, BaseTool] = {t.name: t for t in self._tools}
        self._ckpt_path = _APPROVAL_DB_PATH
        (_ROOT / "data").mkdir(parents=True, exist_ok=True)
        LangGraphProvider._instances.append(self)
        logger.info("LangGraphProvider 初始化完成，共 %d 个工具: %s",
                     len(self._tools), [t.name for t in self._tools])
        logger.info("需要确认的工具: %s",
                     [t.name for t in self._tools if getattr(t, "requires_confirmation", False)])

    # ------------------------------------------------------------------
    # 连接池管理
    # ------------------------------------------------------------------

    @classmethod
    async def _get_pool(cls, db_path: str) -> ConnectionPool:
        """获取或创建连接池（双重检查锁）。"""
        if cls._pool is not None:
            return cls._pool
        async with cls._pool_lock:
            if cls._pool is None:
                cls._pool = ConnectionPool(db_path, min_size=2, max_size=10)
                logger.info("连接池已创建")
        return cls._pool

    @classmethod
    async def close_all(cls) -> None:
        """关闭连接池。在应用关闭时调用。"""
        if cls._pool is not None:
            await cls._pool.close_all()
            cls._pool = None
        cls._instances.clear()

    # ------------------------------------------------------------------
    # 图预编译（双重检查锁）
    # ------------------------------------------------------------------

    async def _get_compiled_graph(self, checkpointer=None):
        """获取预编译的图（只编译一次）。

        注意：由于 checkpointer 是 per-session 的，我们需要为每个 checkpointer 创建一个编译后的图。
        这里使用一个简单的缓存策略。
        """
        # 由于 checkpointer 是 per-connection 的，我们需要为每个 checkpointer 编译图
        # 这是一个简化实现，实际生产环境可能需要更复杂的缓存策略
        graph = self._build_graph()
        return graph.compile(checkpointer=checkpointer)

    def _build_graph(self):
        """构建图结构（不绑定 checkpointer）。"""
        llm_with_tools = (
            self._llm.bind_tools(self._tools) if self._tools else self._llm
        )
        tool_map = self._tool_map
        confirmation_mode = self._confirmation_mode
        workspace_root = self._workspace_root

        def agent_node(state: MessagesState) -> dict:
            logger.info("[agent_node] 使用 %d 条消息调用 LLM", len(state["messages"]))
            response = llm_with_tools.invoke(state["messages"])
            logger.info("[agent_node] LLM 响应: tool_calls=%s, content=%s",
                        bool(response.tool_calls), (response.content or "")[:100])
            return {"messages": [response]}

        def human_review_node(state: MessagesState) -> dict:
            last_msg = state["messages"][-1]
            tool_names = [tc["name"] for tc in last_msg.tool_calls]
            logger.info("[human_review_node] 中断，等待确认工具: %s", tool_names)
            user_decision = interrupt({
                "type": "ask_human_approval",
                "tool_calls": last_msg.tool_calls,
                "message": "是否允许执行此工具？",
            })
            logger.info("[human_review_node] 用户决定: %s", user_decision)
            if isinstance(user_decision, dict):
                approved = user_decision.get("approved", False)
            else:
                approved = bool(user_decision)
            if not approved:
                logger.info("[human_review_node] 已拒绝，返回 ToolMessage")
                return {"messages": [ToolMessage(
                    content="工具调用已被用户拒绝。",
                    tool_call_id=last_msg.tool_calls[0]["id"],
                )]}
            logger.info("[human_review_node] 已批准，返回空结果（保留 tool_calls）")
            return {}

        def tools_node(state: MessagesState) -> dict:
            from langgraph.prebuilt import ToolNode
            logger.info("[tools_node] 执行工具")
            result = ToolNode(self._tools).invoke(state)
            logger.info("[tools_node] 执行完成")
            return result

        # ---- Path validator node (Layer 2 defence) ----
        _PATH_PARAM_KEYWORDS = {"path", "dir", "folder", "root"}

        def path_validator_node(state: MessagesState) -> dict:
            last_msg = state["messages"][-1]
            tool_calls = getattr(last_msg, "tool_calls", [])
            if not tool_calls:
                return {"messages": []}

            validated_calls = []
            for tc in tool_calls:
                args = tc.get("args", {})
                tool = self._tool_map.get(tc["name"])
                allow_external = getattr(tool, "_allow_external_paths", False) if tool else False

                for key, value in list(args.items()):
                    if not isinstance(value, str) or not value.strip():
                        continue
                    if not any(kw in key.lower() for kw in _PATH_PARAM_KEYWORDS):
                        continue
                    try:
                        if allow_external:
                            args[key] = str(resolve_path(value))
                        else:
                            args[key] = str(validate_path(value))
                    except ValueError as e:
                        logger.info("[path_validator] 拒绝: tool=%s, arg=%s, error=%s",
                                    tc["name"], key, e)
                        return {"messages": [ToolMessage(
                            content=f"路径校验失败: {e}。请使用工作区内的合法路径。",
                            tool_call_id=tc["id"],
                        )]}

                tc["args"] = args
                validated_calls.append(tc)

            last_msg.tool_calls = validated_calls
            logger.info("[path_validator] 全部通过，%d 个 tool_calls", len(validated_calls))
            return {"messages": [last_msg]}

        def route_after_agent(state: MessagesState) -> str:
            last_msg = state["messages"][-1]
            if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
                logger.info("[route_after_agent] 无 tool_calls -> END")
                return END

            if confirmation_mode == "full_access":
                logger.info("[route_after_agent] full_access 模式 -> path_validator")
                return "path_validator"

            if confirmation_mode == "plan":
                logger.info("[route_after_agent] plan 模式 -> human_review（全部确认）")
                return "human_review"

            # "confirm" 模式：对每个工具动态检查是否需要确认
            for tc in last_msg.tool_calls:
                tool = tool_map.get(tc["name"])
                if tool is None:
                    continue
                needs_confirm = tool.check_requires_confirmation(**tc.get("args", {}))
                if needs_confirm:
                    # 检查是否已允许（指纹匹配）
                    if confirmation_manager.check_fingerprint_allowed(workspace_root, tc["name"], tc.get("args", {})):
                        logger.info("[route_after_agent] 工具 '%s' 已允许（指纹匹配）-> path_validator", tc["name"])
                        continue
                    logger.info("[route_after_agent] 工具 '%s' 需要确认 -> human_review", tc["name"])
                    return "human_review"
            logger.info("[route_after_agent] 无需确认 -> path_validator")
            return "path_validator"

        def route_after_review(state: MessagesState) -> str:
            last_msg = state["messages"][-1]
            if isinstance(last_msg, ToolMessage):
                logger.info("[route_after_review] 已拒绝（ToolMessage）-> agent")
                return "agent"
            logger.info("[route_after_review] 已批准（非 ToolMessage）-> path_validator")
            return "path_validator"

        def route_after_validator(state: MessagesState) -> str:
            last_msg = state["messages"][-1]
            if isinstance(last_msg, ToolMessage):
                logger.info("[route_after_validator] 校验失败 -> agent（自纠错）")
                return "agent"
            logger.info("[route_after_validator] 校验通过 -> tools")
            return "tools"

        graph = StateGraph(MessagesState)
        graph.add_node("agent", agent_node)
        graph.add_node("human_review", human_review_node)
        graph.add_node("path_validator", path_validator_node)
        graph.add_node("tools", tools_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", route_after_agent, {
            "human_review": "human_review",
            "path_validator": "path_validator",
            END: END,
        })
        graph.add_conditional_edges("human_review", route_after_review, {
            "agent": "agent",
            "path_validator": "path_validator",
        })
        graph.add_conditional_edges("path_validator", route_after_validator, {
            "agent": "agent",
            "tools": "tools",
        })
        graph.add_edge("tools", "agent")
        return graph

    # ------------------------------------------------------------------
    # 消息转换
    # ------------------------------------------------------------------

    def _to_lc_messages(self, state: AgentState) -> list[BaseMessage]:
        lc: list[BaseMessage] = []
        if self._system_message:
            lc.append(SystemMessage(content=self._system_message))
        for msg in state.messages:
            if msg.role == "system":
                lc.append(SystemMessage(content=msg.content))
            elif msg.role == "user":
                lc.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                tool_calls = msg.metadata.get("tool_calls")
                if tool_calls:
                    lc.append(AIMessage(content=msg.content or "", tool_calls=tool_calls))
                else:
                    lc.append(AIMessage(content=msg.content))
            elif msg.role == "tool":
                lc.append(ToolMessage(
                    content=msg.content,
                    tool_call_id=msg.metadata.get("tool_call_id", ""),
                ))
        return lc

    # ------------------------------------------------------------------
    # 核心：基于 LangGraph 中断的流式执行
    # ------------------------------------------------------------------

    async def __call__(self, state: AgentState, *, session_id: str = "default") -> AsyncIterable[AgentMessage]:
        """基于中断机制执行代理图并进行人类确认。"""
        try:
            # 获取连接池
            pool = await self._get_pool(self._ckpt_path)

            # 从连接池获取连接，创建 checkpointer
            async with pool.acquire() as conn:
                checkpointer = AsyncSqliteSaver(conn)

                # 获取编译后的图（每个 checkpointer 需要单独编译）
                compiled_graph = await self._get_compiled_graph(checkpointer)

                thread_id = session_id
                config = {"configurable": {"thread_id": thread_id}}
                lc_messages = self._to_lc_messages(state)
                current_input: Any = {"messages": lc_messages}
                logger.info("[__call__] 开始执行，thread_id=%s，共 %d 条消息", thread_id, len(lc_messages))

                _round = 0
                while True:
                    _round += 1
                    logger.info("[__call__] 第 %d 轮", _round)
                    final_messages: list[AIMessage] = []

                    async for event in compiled_graph.astream(
                        current_input,
                        config=config,
                        stream_mode=["updates", "messages"],
                        subgraph=False,
                    ):
                        # 检查任务是否被取消
                        task = asyncio.current_task()
                        if task and task.cancelled():
                            logger.info("[__call__] 任务被取消，session_id=%s", session_id)
                            raise asyncio.CancelledError()

                        mode, data = event

                        if mode == "messages":
                            msg, _metadata = data
                            if isinstance(msg, AIMessageChunk):
                                token = msg.content or ""
                                if token:
                                    yield AgentMessage(
                                        role="assistant",
                                        content=token,
                                        metadata={"chunk": True},
                                    )

                        elif mode == "updates" and data and isinstance(data, dict):
                            for node_name, update in data.items():
                                if not update or not isinstance(update, dict):
                                    continue
                                msgs = update.get("messages", [])
                                logger.info("[__call__] 节点 '%s' 更新: %d 条消息", node_name, len(msgs))
                                for msg in msgs:
                                    if isinstance(msg, AIMessage):
                                        logger.info("[__call__] AIMessage: tool_calls=%s, content=%s",
                                                    bool(msg.tool_calls), (msg.content or "")[:80])
                                        final_messages.append(msg)

                    # --- 检查中断 ---
                    snapshot = await compiled_graph.aget_state(config)
                    logger.info("[__call__] 流结束后: snapshot.next=%s, tasks=%d",
                                snapshot.next, len(snapshot.tasks) if snapshot.tasks else 0)
                    has_interrupt = False

                    if snapshot.tasks:
                        for task_node in snapshot.tasks:
                            logger.info("[__call__] 任务: %s, interrupts=%s",
                                        task_node.name if hasattr(task_node, 'name') else '?',
                                        len(task_node.interrupts) if task_node.interrupts else 0)
                            if not task_node.interrupts:
                                continue
                            has_interrupt = True
                            for intr in task_node.interrupts:
                                payload = intr.value
                                tool_calls = payload.get("tool_calls", [])
                                logger.info("[__call__] 检测到中断: %d 个 tool_calls", len(tool_calls))

                                for tc in tool_calls:
                                    yield AgentMessage(
                                        role="assistant",
                                        content="",
                                        metadata={
                                            "chunk": True,
                                            "status": {
                                                "status": "tool_start",
                                                "name": tc["name"],
                                                "args": tc["args"],
                                            },
                                        },
                                    )

                                    req = confirmation_manager.create_request(
                                        tool_name=tc["name"],
                                        tool_args=tc["args"],
                                        workspace_root=self._workspace_root,
                                    )
                                    logger.info("[__call__] 发出 confirmation_required 请求: '%s' (id=%s)",
                                                tc["name"], req.confirmation_id)

                                    yield AgentMessage(
                                        role="assistant",
                                        content="",
                                        metadata={
                                            "chunk": True,
                                            "status": {
                                                "status": "confirmation_required",
                                                "confirmation_id": req.confirmation_id,
                                                "tool_name": tc["name"],
                                                "tool_args": tc["args"],
                                                "description": req.description,
                                                "high_risk": is_high_risk(tc["name"], tc["args"]),
                                            },
                                        },
                                    )

                                    logger.info("[__call__] 等待用户决定...")
                                    try:
                                        approved = await confirmation_manager.wait_for_decision(
                                            req.confirmation_id, timeout=300.0
                                        )
                                    except TimeoutError:
                                        yield AgentMessage(
                                            role="assistant",
                                            content="",
                                            metadata={
                                                "chunk": True,
                                                "status": {
                                                    "status": "confirmation_expired",
                                                    "confirmation_id": req.confirmation_id,
                                                    "tool_name": tc["name"],
                                                },
                                            },
                                        )
                                        approved = False

                                    logger.info("[__call__] 决定结果: %s", approved)
                                    current_input = Command(resume={"approved": approved})

                    if has_interrupt:
                        logger.info("[__call__] 存在中断，继续下一轮")
                        continue

                    # --- 无中断 ---
                    response = final_messages[-1] if final_messages else None
                    logger.info("[__call__] 无中断。final_messages=%d, response=%s",
                                len(final_messages), bool(response))
                    if response is None:
                        break

                    if not response.tool_calls:
                        logger.info("[__call__] 最终响应（无 tool_calls）: %s", response.content[:100])
                        state.append(AgentMessage(role="assistant", content=response.content))
                        yield AgentMessage(role="assistant", content=response.content)
                        # 发送 token usage 数据
                        usage = getattr(response, "usage_metadata", None)
                        if usage:
                            yield AgentMessage(
                                role="assistant", content="",
                                metadata={
                                    "chunk": True,
                                    "status": {
                                        "status": "usage",
                                        "prompt_tokens": usage.get("input_tokens", 0),
                                        "completion_tokens": usage.get("output_tokens", 0),
                                        "total_tokens": usage.get("total_tokens", 0),
                                    },
                                },
                            )
                        return

                    logger.info("[__call__] 响应包含 tool_calls 但无中断，跳出循环")
                    break

                logger.info("[__call__] 退出循环，发出 stop")
                state.append(AgentMessage(role="assistant", content="", metadata={"stop": True}))

        except asyncio.CancelledError:
            # 任务被取消，记录日志并重新抛出
            logger.info("[__call__] 任务被取消，session_id=%s", session_id)
            raise
