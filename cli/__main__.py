"""CLI entry point for the assistant agent.

Usage:
    python -m cli

Reads configuration from .env file (see .env.example).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from web.llm.openai_adapter import OpenAIAdapter
from web.llm.provider import build_agent_provider
from cli.runner import CLIRunner, AgentRunnerConfig


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Create a .env file or export the variable."
        )

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    system_message = os.getenv(
        "SYSTEM_MESSAGE", "你叫coco，根据用户给的消息，帮助用户解决问题，语气要温和。"
    )
    stream = os.getenv("OPENAI_STREAM", "true").strip().lower() in {
        "1", "true", "yes",
    }

    provider = build_provider(
        api_key=api_key,
        model=model,
        base_url=base_url,
        system_message=system_message,
        stream=stream,
    )

    runner = CLIRunner(
        provider=provider,
        config=AgentRunnerConfig(
            name="langgraph-agent",
            system_message=system_message,
            stream=stream,
        ),
    )
    runner.run_cli()


if __name__ == "__main__":
    main()
