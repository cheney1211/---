"""OpenAI-compatible provider built on LangChain + LangGraph.

Supports both streaming and non-streaming modes.
When streaming, yields chunk AgentMessages with metadata["chunk"]=True
followed by the final complete AgentMessage.
"""

from __future__ import annotations

from typing import Iterable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph

from assistant.core import AgentMessage, AgentState
from assistant.loop import MessageProvider


def _to_lc_messages(messages: list[AgentMessage], *, system_message: str | None = None) -> list:
    """Convert our AgentMessage list to LangChain message objects."""
    lc = []
    if system_message and (not messages or messages[0].role != "system"):
        lc.append(SystemMessage(content=system_message))
    for msg in messages:
        if msg.role == "system":
            lc.append(SystemMessage(content=msg.content))
        elif msg.role == "user":
            lc.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc.append(AIMessage(content=msg.content))
    return lc


def _build_graph(
    *,
    model: str,
    api_key: str,
    base_url: str | None = None,
    temperature: float = 0.7,
) -> callable:
    """Build a single-node LangGraph agent graph."""
    llm_kwargs: dict = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
    }
    if base_url:
        llm_kwargs["base_url"] = base_url

    llm = ChatOpenAI(**llm_kwargs)

    def agent_node(state: MessagesState) -> dict:
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()


def build_provider(
    *,
    model: str,
    api_key: str,
    base_url: str | None = None,
    temperature: float = 0.7,
    system_message: str | None = None,
    stream: bool = False,
) -> MessageProvider:
    """Return a MessageProvider backed by a LangGraph + LangChain OpenAI agent.

    When *stream* is True the provider:
      1. Yields incremental ``AgentMessage(chunk=True)`` for every token.
      2. Yields one final ``AgentMessage`` (no chunk flag) with the full text.

    When *stream* is False it behaves like before: one complete message.
    """
    llm_kwargs: dict = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
    }
    if base_url:
        llm_kwargs["base_url"] = base_url

    llm = ChatOpenAI(**llm_kwargs)
    app = _build_graph(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    ) if not stream else None  # graph not needed for streaming path

    def provider(state: AgentState) -> Iterable[AgentMessage]:
        lc_messages = _to_lc_messages(state.messages, system_message=system_message)

        if stream:
            # -- streaming path: token-level via ChatOpenAI.stream() ---------
            full_text_parts: list[str] = []
            for chunk in llm.stream(lc_messages):
                token = chunk.content or ""
                if token:
                    full_text_parts.append(token)
                    yield AgentMessage(
                        role="assistant",
                        content=token,
                        metadata={"chunk": True},
                    )
            # Final complete message (stored in state by the loop)
            yield AgentMessage(role="assistant", content="".join(full_text_parts))
        else:
            # -- non-streaming path: via LangGraph graph ---------------------
            assert app is not None
            result = app.invoke({"messages": lc_messages})
            ai_msg: AIMessage = result["messages"][-1]
            yield AgentMessage(role="assistant", content=ai_msg.content)

    return provider
