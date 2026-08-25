"""CLI entry point for the assistant agent.

Usage:
    python -m cli

Reads configuration from .env file (see .env.example).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from web.llm import get_adapter, get_provider, get_default_provider_name, get_default_system_message
from assistant.tools import get_tools, register as register_tool
from assistant.tools.builtin.call_skill import CallSkillTool, configure as configure_call_skill
from assistant.skills import build_skills_system_prompt
from cli.runner import CLIRunner, AgentRunnerConfig


def main() -> None:
    provider_name = get_default_provider_name()
    base_system = get_default_system_message()
    skill_index = build_skills_system_prompt()
    system_message = f"{base_system}\n\n{skill_index}" if skill_index else base_system
    stream = os.getenv("OPENAI_STREAM", "true").strip().lower() in {
        "1", "true", "yes",
    }

    # Configure call_skill tool with LLM and register it
    adapter = get_adapter(provider_name)
    configure_call_skill(adapter.llm, base_system)
    register_tool(CallSkillTool())

    tools = get_tools()
    provider = get_provider(provider_name, system_message=system_message, tools=tools)

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