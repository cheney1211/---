"""CLI runner: extends AgentRunner with a prompt_toolkit TUI."""

from __future__ import annotations

import asyncio
import shutil

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

from assistant.runner import AgentRunner, AgentRunnerConfig
from assistant.skills import list_skills, reload_skills

_COMMANDS = WordCompleter(
    ["/exit", "/quit", "/help", "/skills", "/reload_skills"],
    ignore_case=True,
    sentence=True,
)


class CLIRunner(AgentRunner):
    """CLI chat using normal terminal output (native scrollback)."""

    def run_cli(self, *, first_message: str | None = None) -> None:
        session = PromptSession(completer=_COMMANDS)
        state = self._state

        def print_separator() -> None:
            width = shutil.get_terminal_size((80, 24)).columns
            print("\u2500" * width)

        def print_message(role: str, content: str) -> None:
            if role == "user":
                print(f"{self.config.user_name}\uff1a{content}")
            elif role == "agent":
                print(f"{self.config.agent_name}: {content}", end="")
            else:
                print(content, end="")

        def handle_reply(reply: str | None) -> None:
            if reply:
                print(f"{self.config.agent_name}: {reply}")

        async def run() -> None:
            nonlocal state
            print(self.config.agent_name)
            print()

            if first_message:
                print_message("user", first_message)
                on_msg = make_on_message()
                if self._is_async_provider():
                    state = await self.acreate_state(first_message, on_message=on_msg)
                else:
                    state = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: self.create_state(first_message, on_message=on_msg),
                    )
                if not self.config.stream:
                    handle_reply(self._last_assistant_message(state))

            while True:
                try:
                    text = await session.prompt_async("> ")
                except (EOFError, KeyboardInterrupt):
                    break

                text = text.strip()
                if not text:
                    continue

                cmd = text.lower()
                if cmd in {"/exit", "/quit"}:
                    break

                if cmd == "/help":
                    print("/help")
                    print("  /exit    Exit the assistant")
                    print("  /quit    Exit the assistant")
                    print("  /skills  List available skills")
                    print("  /reload_skills  Reload skills from disk")
                    print("  /help    Show this help")
                    print()
                    continue

                if cmd == "/reload_skills":
                    print("/reload_skills")
                    try:
                        count = reload_skills()
                        print(f"  Reloaded {count} skill(s)")
                    except Exception as exc:
                        print(f"  Reload failed: {exc}")
                    print()
                    continue

                if cmd == "/skills":
                    print("/skills")
                    skills = list_skills()
                    if not skills:
                        print("  (none)")
                    else:
                        for skill in skills:
                            tags = ", ".join(skill.get("tags") or []) or "-"
                            print(
                                f"  {skill['name']} \u2014 {skill['description']} "
                                f"[v{skill.get('version', '?')} by {skill.get('author', '?')}] "
                                f"[tags: {tags}]"
                            )
                    print()
                    continue

                print_message("user", text)

                def make_on_message():
                    printed = [False]

                    def on_message(msg):
                        if msg.metadata.get("chunk"):
                            if not printed[0]:
                                print(f"{self.config.agent_name}: ", end="", flush=True)
                                printed[0] = True
                            print(msg.content, end="", flush=True)
                        elif msg.role == "assistant":
                            if not printed[0]:
                                print(f"{self.config.agent_name}: ", end="", flush=True)
                                printed[0] = True
                            print()
                    return on_message

                if self._is_async_provider():
                    state = await self.acontinue_state(
                        state, text, on_message=make_on_message()
                    )
                else:
                    def process():
                        return self.continue_state(state, text, on_message=make_on_message())

                    state = await asyncio.get_running_loop().run_in_executor(
                        None, process
                    )

                if not self.config.stream:
                    handle_reply(self._last_assistant_message(state))

            print("Goodbye!")

        asyncio.run(run())
