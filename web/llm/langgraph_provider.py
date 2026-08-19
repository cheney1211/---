"""LangGraph-based agent provider.

用 LangGraph StateGraph 替代手写 while 循环，驱动 agent ↔ tool 交互。
图结构:
    START → agent → should_continue? → tools → agent → ... → END
"""

from __future__ import annotations

from typing import Any, AsyncIterable, List, Optional

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
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from assistant.core import AgentMessage, AgentState


class LangGraphProvider:
    """用 LangGraph 状态图驱动的 Agent Provider。

    替代旧的 AssistantLLMProvider，用图的节点/边/条件路由
    实现 agent ↔ tools 循环，而非手写 while + if。
    """

    def __init__(
        self,
        llm: BaseChatModel,
        *,
        tools: Optional[List[BaseTool]] = None,
        system_message: str | None = None,
        max_tool_rounds: int = 5,
    ) -> None:
        self._llm = llm
        self._tools = tools or []
        self._system_message = system_message
        self._max_tool_rounds = max_tool_rounds
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # 图构建
    # ------------------------------------------------------------------

    def _build_graph(self):
        """构建 LangGraph 状态图。

        节点:
          - agent: 调用 LLM（绑定工具定义）
          - tools: 执行 LLM 请求的工具调用

        边:
          - agent → should_continue (条件)
          - should_continue → tools (有 tool_calls)
          - should_continue → END (纯文本回复)
          - tools → agent (工具执行完，回到 agent 让 LLM 总结)
        """
        llm_with_tools = (
            self._llm.bind_tools(self._tools) if self._tools else self._llm
        )

        # --- 节点 ---
        def agent_node(state: MessagesState) -> dict:
            response = llm_with_tools.invoke(state["messages"])
            return {"messages": [response]}

        # --- 条件路由 ---
        def should_continue(state: MessagesState) -> str:
            last_msg = state["messages"][-1]
            if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
                return "tools"
            return END

        # --- 组装图 ---
        graph = StateGraph(MessagesState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", ToolNode(self._tools))
        graph.set_entry_point("agent")
        graph.add_conditional_edges(
            "agent",
            should_continue,
            {"tools": "tools", END: END},
        )
        graph.add_edge("tools", "agent")

        return graph.compile()

    # ------------------------------------------------------------------
    # 消息转换: AgentState ↔ LangChain messages
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
                    lc.append(
                        AIMessage(content=msg.content or "", tool_calls=tool_calls)
                    )
                else:
                    lc.append(AIMessage(content=msg.content))
            elif msg.role == "tool":
                lc.append(
                    ToolMessage(
                        content=msg.content,
                        tool_call_id=msg.metadata.get("tool_call_id", ""),
                    )
                )
        return lc

    # ------------------------------------------------------------------
    # 核心: 流式执行图
    # ------------------------------------------------------------------

    async def __call__(self, state: AgentState) -> AsyncIterable[AgentMessage]:
        """执行图并流式返回 AgentMessage。

        yield 的消息分三类:
          1. chunk=True, 有 content → 流式 token，前端逐字显示
          2. chunk=True, 有 status → 工具调用状态，前端显示进度
          3. 无 chunk 标记 → 最终回复，前端存入对话 + 显示

        同时把 tool_calls / tool results / 最终回复写入 AgentState。
        """
        lc_messages = self._to_lc_messages(state)
        input_state = {"messages": lc_messages}

        async for msg, metadata in self._graph.astream(
            input_state,
            stream_mode="messages",
            recursion_limit=self._max_tool_rounds * 2 + 1,
        ):
            # --- 流式 token ---
            if isinstance(msg, AIMessageChunk):
                token = msg.content or ""
                if token:
                    yield AgentMessage(
                        role="assistant",
                        content=token,
                        metadata={"chunk": True},
                    )

            # --- 完整 LLM 回复（可能含 tool_calls）---
            elif isinstance(msg, AIMessage):
                if msg.tool_calls:
                    # 中间消息: LLM 决定调用工具
                    state.append(
                        AgentMessage(
                            role="assistant",
                            content=msg.content or "",
                            metadata={"tool_calls": msg.tool_calls},
                        )
                    )
                    for tc in msg.tool_calls:
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
                else:
                    # 最终文本回复
                    state.append(AgentMessage(role="assistant", content=msg.content))
                    yield AgentMessage(role="assistant", content=msg.content)

            # --- 工具执行结果 ---
            elif isinstance(msg, ToolMessage):
                state.append(
                    AgentMessage(
                        role="tool",
                        content=msg.content,
                        metadata={"tool_call_id": msg.tool_call_id},
                    )
                )
                yield AgentMessage(
                    role="assistant",
                    content="",
                    metadata={
                        "chunk": True,
                        "status": {
                            "status": "tool_end",
                            "name": msg.name or "tool",
                            "output": msg.content,
                        },
                    },
                )
    async def __call__(self, state: AgentState) -> AsyncIterable[AgentMessage]:
        """执行图并流式返回 AgentMessage。

        使用 stream_mode=["updates", "messages"] 双流模式:
          - "messages"  → AIMessageChunk，逐 token 流式
          - "updates"   → 每个节点执行完的完整消息 (AIMessage / ToolMessage)

        yield 的消息分三类:
          1. chunk=True, 有 content → 流式 token，前端逐字显示
          2. chunk=True, 有 status → 工具调用状态，前端显示进度
          3. 无 chunk 标记 → 最终回复，前端存入对话 + 显示
        """
        lc_messages = self._to_lc_messages(state)
        input_state = {"messages": lc_messages}

        async for event in self._graph.astream(
            input_state,
            stream_mode=["updates", "messages"],
            recursion_limit=self._max_tool_rounds * 2 + 1,
        ):
            mode, data = event

            # ---- messages 模式: 逐 token 流式 ----
            if mode == "messages":
                msg, metadata = data
                if isinstance(msg, AIMessageChunk):
                    token = msg.content or ""
                    if token:
                        yield AgentMessage(
                            role="assistant",
                            content=token,
                            metadata={"chunk": True},
                        )

            # ---- updates 模式: 节点级完整输出 ----
            elif mode == "updates":
                for node_name, update in data.items():
                    messages = update.get("messages", [])
                    for msg in messages:
                        # LLM 完整回复
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                # LLM 决定调用工具
                                state.append(
                                    AgentMessage(
                                        role="assistant",
                                        content=msg.content or "",
                                        metadata={"tool_calls": msg.tool_calls},
                                    )
                                )
                                for tc in msg.tool_calls:
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
                            else:
                                # 最终文本回复
                                state.append(
                                    AgentMessage(role="assistant", content=msg.content)
                                )
                                yield AgentMessage(
                                    role="assistant", content=msg.content
                                )

                        # 工具执行结果
                        elif isinstance(msg, ToolMessage):
                            state.append(
                                AgentMessage(
                                    role="tool",
                                    content=msg.content,
                                    metadata={"tool_call_id": msg.tool_call_id},
                                )
                            )
                            yield AgentMessage(
                                role="assistant",
                                content="",
                                metadata={
                                    "chunk": True,
                                    "status": {
                                        "status": "tool_end",
                                        "name": msg.name or "tool",
                                        "output": msg.content,
                                    },
                                },
                            )
