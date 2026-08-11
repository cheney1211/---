"""Environment-based entry point for the assistant agent.

Reads configuration from environment variables (or .env file):
    OPENAI_API_KEY   - required
    OPENAI_MODEL     - optional, defaults to gpt-4o-mini
    OPENAI_BASE_URL  - optional, defaults to https://api.openai.com/v1
    SYSTEM_MESSAGE   - optional, defaults to a concise assistant prompt
    OPENAI_STREAM    - optional, "true" to enable streaming (default: true)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from assistant.providers.langgraph_openai import build_provider
from assistant.runner import AgentRunner, AgentRunnerConfig


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Create a .env file or export the variable."
        )

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    system_message = os.getenv("SYSTEM_MESSAGE", "你叫coco，根据用户给的消息，帮助用户解决问题，语气要温和。")
    stream = os.getenv("OPENAI_STREAM", "true").strip().lower() in {"1", "true", "yes"}

    provider = build_provider(
        api_key=api_key,
        model=model,
        base_url=base_url,
        system_message=system_message,
        stream=stream,
    )

    runner = AgentRunner(
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
