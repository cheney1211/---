"""CLI entry point for the assistant agent.

Usage:
    python -m cli

Reads configuration from .env file (see .env.example).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from web.llm import get_provider, get_default_provider_name, get_default_system_message
from cli.runner import CLIRunner, AgentRunnerConfig


def main() -> None:
    provider_name = get_default_provider_name()
    system_message = get_default_system_message()
    stream = os.getenv("OPENAI_STREAM", "true").strip().lower() in {
        "1", "true", "yes",
    }

    provider = get_provider(provider_name, system_message=system_message)

    runner = CLIRunner(
        provider=provider,
        config=AgentRunnerConfig(
            name=f"{provider_name}-agent",
            system_message=system_message,
            stream=stream,
        ),
    )
    runner.run_cli()


if __name__ == "__main__":
    main()
