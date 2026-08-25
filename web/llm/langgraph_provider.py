"""LangGraph-based agent provider with human-in-the-loop confirmation.

Graph structure:
    agent -> human_review (interrupt) -> tools -> agent -> ...
    agent -> tools -> agent -> ...  (no confirmation needed)
    human_review -> agent  (rejected, skip tools)

The human_review node sits BEFORE tools and calls interrupt() to pause
the graph. Tool calls are preserved in the state until the user decides.
"""

from __future__ import annotations

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
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.types import interrupt, Command

from assistant.core import AgentMessage, AgentState
from assistant.tools.confirmation import ConfirmationManager

logger = logging.getLogger("langgraph_provider")

confirmation_manager = ConfirmationManager()


class LangGraphProvider:
    """Agent provider with LangGraph interrupt-based confirmation."""

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
        self._tool_map: Dict[str, BaseTool] = {t.name: t for t in self._tools}
        _ROOT = Path(__file__).resolve().parent.parent.parent
        _ckpt_path = _ROOT / "data" / "langgraph_checkpoints.db"
        _ckpt_path.parent.mkdir(parents=True, exist_ok=True)
        self._ckpt_path = str(_ckpt_path)
        self._conn = None
        self._checkpointer = None
        self._graph = None
        logger.info("LangGraphProvider initialized with %d tools: %s",
                     len(self._tools), [t.name for t in self._tools])
        logger.info("Tools requiring confirmation: %s",
                     [t.name for t in self._tools if getattr(t, "requires_confirmation", False)])

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self, checkpointer):
        llm_with_tools = (
            self._llm.bind_tools(self._tools) if self._tools else self._llm
        )
        tool_map = self._tool_map

        def agent_node(state: MessagesState) -> dict:
            logger.info("[agent_node] Invoking LLM with %d messages", len(state["messages"]))
            response = llm_with_tools.invoke(state["messages"])
            logger.info("[agent_node] LLM response: tool_calls=%s, content=%s",
                        bool(response.tool_calls), (response.content or "")[:100])
            return {"messages": [response]}

        def human_review_node(state: MessagesState) -> dict:
            last_msg = state["messages"][-1]
            tool_names = [tc["name"] for tc in last_msg.tool_calls]
            logger.info("[human_review_node] INTERRUPT for tools: %s", tool_names)
            user_decision = interrupt({
                "type": "ask_human_approval",
                "tool_calls": last_msg.tool_calls,
                "message": "是否允许执行此工具？",
            })
            logger.info("[human_review_node] User decision: %s", user_decision)
            if isinstance(user_decision, dict):
                approved = user_decision.get("approved", False)
            else:
                approved = bool(user_decision)
            if not approved:
                logger.info("[human_review_node] Rejected, returning ToolMessage")
                return {"messages": [ToolMessage(
                    content="工具调用已被用户拒绝。",
                    tool_call_id=last_msg.tool_calls[0]["id"],
                )]}
            logger.info("[human_review_node] Approved, returning empty (tool_calls preserved)")
            return {}

        def tools_node(state: MessagesState) -> dict:
            from langgraph.prebuilt import ToolNode
            logger.info("[tools_node] Executing tools")
            result = ToolNode(self._tools).invoke(state)
            logger.info("[tools_node] Done")
            return result

        def route_after_agent(state: MessagesState) -> str:
            last_msg = state["messages"][-1]
            if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
                logger.info("[route_after_agent] No tool_calls -> END")
                return END
            for tc in last_msg.tool_calls:
                tool = tool_map.get(tc["name"])
                if getattr(tool, "requires_confirmation", False):
                    logger.info("[route_after_agent] Tool '%s' needs confirmation -> human_review", tc["name"])
                    return "human_review"
            logger.info("[route_after_agent] No confirmation needed -> tools")
            return "tools"

        def route_after_review(state: MessagesState) -> str:
            last_msg = state["messages"][-1]
            if isinstance(last_msg, ToolMessage):
                logger.info("[route_after_review] Rejected (ToolMessage) -> agent")
                return "agent"
            logger.info("[route_after_review] Approved (no ToolMessage) -> tools")
            return "tools"

        graph = StateGraph(MessagesState)
        graph.add_node("agent", agent_node)
        graph.add_node("human_review", human_review_node)
        graph.add_node("tools", tools_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", route_after_agent, {
            "human_review": "human_review",
            "tools": "tools",
            END: END,
        })
        graph.add_conditional_edges("human_review", route_after_review, {
            "agent": "agent",
            "tools": "tools",
        })
        graph.add_edge("tools", "agent")
        return graph.compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------
    # Message conversion
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
    # Core: streaming execution with LangGraph interrupt
    # ------------------------------------------------------------------

    async def __call__(self, state: AgentState, *, session_id: str = "default") -> AsyncIterable[AgentMessage]:
        """Execute the agent graph with interrupt-based confirmation."""
        # Lazy init checkpointer and graph
        if self._checkpointer is None:
            self._conn = await aiosqlite.connect(self._ckpt_path)
            self._checkpointer = AsyncSqliteSaver(self._conn)
            self._graph = self._build_graph(self._checkpointer)
        thread_id = session_id
        config = {"configurable": {"thread_id": thread_id}}
        lc_messages = self._to_lc_messages(state)
        current_input: Any = {"messages": lc_messages}
        logger.info("[__call__] Starting with thread_id=%s, %d messages", thread_id, len(lc_messages))

        for _round in range(self._max_tool_rounds):
            logger.info("[__call__] Round %d", _round + 1)
            final_messages: list[AIMessage] = []

            async for event in self._graph.astream(
                current_input,
                config=config,
                stream_mode=["updates", "messages"],
                subgraph=False,
            ):
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
                        logger.info("[__call__] Update from node '%s': %d messages", node_name, len(msgs))
                        for msg in msgs:
                            if isinstance(msg, AIMessage):
                                logger.info("[__call__] AIMessage: tool_calls=%s, content=%s",
                                            bool(msg.tool_calls), (msg.content or "")[:80])
                                final_messages.append(msg)

            # --- Check for interrupt ---
            snapshot = await self._graph.aget_state(config)
            logger.info("[__call__] After stream: snapshot.next=%s, tasks=%d",
                        snapshot.next, len(snapshot.tasks) if snapshot.tasks else 0)
            has_interrupt = False

            if snapshot.tasks:
                for task in snapshot.tasks:
                    logger.info("[__call__] Task: %s, interrupts=%s",
                                task.name if hasattr(task, 'name') else '?',
                                len(task.interrupts) if task.interrupts else 0)
                    if not task.interrupts:
                        continue
                    has_interrupt = True
                    for intr in task.interrupts:
                        payload = intr.value
                        tool_calls = payload.get("tool_calls", [])
                        logger.info("[__call__] INTERRUPT DETECTED: %d tool_calls", len(tool_calls))

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
                            )
                            logger.info("[__call__] Yielding confirmation_required for '%s' (id=%s)",
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
                                    },
                                },
                            )

                            logger.info("[__call__] Waiting for user decision...")
                            try:
                                approved = await confirmation_manager.wait_for_decision(
                                    req.confirmation_id, timeout=300.0
                                )
                            except TimeoutError:
                                approved = False

                            logger.info("[__call__] Decision: %s", approved)
                            current_input = Command(resume={"approved": approved})

            if has_interrupt:
                logger.info("[__call__] Had interrupt, continuing to next round")
                continue

            # --- No interrupt ---
            response = final_messages[-1] if final_messages else None
            logger.info("[__call__] No interrupt. final_messages=%d, response=%s",
                        len(final_messages), bool(response))
            if response is None:
                break

            if not response.tool_calls:
                logger.info("[__call__] Final response (no tool_calls): %s", response.content[:100])
                state.append(AgentMessage(role="assistant", content=response.content))
                yield AgentMessage(role="assistant", content=response.content)
                return

            logger.info("[__call__] Response has tool_calls but no interrupt, breaking")
            break

        logger.info("[__call__] Exited loop, yielding stop")
        state.append(AgentMessage(role="assistant", content="", metadata={"stop": True}))