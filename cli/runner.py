"""CLI runner: extends AgentRunner with a prompt_toolkit TUI."""

from __future__ import annotations

import asyncio
import shutil

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.styles import Style

from assistant.runner import AgentRunner, AgentRunnerConfig

_COMMANDS = WordCompleter(
    ["/exit", "/quit", "/help"],
    ignore_case=True,
    sentence=True,
)


class CLIRunner(AgentRunner):
    """AgentRunner with a full-screen prompt_toolkit chat interface."""

    def run_cli(self, *, first_message: str | None = None) -> None:
        chat_fragments: list = []
        prefix_printed = [False]
        pending_input: list[str | None] = [None]
        should_exit = [False]
        processing = [False]
        state = self._state

        chat_fragments.append(("class:header", f"{self.config.agent_name}\n"))
        chat_fragments.append(("", "\n"))

        def get_chat_text():
            return chat_fragments

        def get_separator():
            width = shutil.get_terminal_size((80, 24)).columns
            return [("class:sep", "\u2500" * width)]

        input_buffer = Buffer(completer=_COMMANDS)
        input_window = Window(height=1, content=BufferControl(buffer=input_buffer))

        output_window = Window(
            content=FormattedTextControl(text=get_chat_text),
            wrap_lines=True,
            always_hide_cursor=True,
            right_margins=[ScrollbarMargin()],
        )

        layout = Layout(
            HSplit([
                output_window,
                Window(height=1, content=FormattedTextControl(text=get_separator)),
                input_window,
                Window(height=1, content=FormattedTextControl(text=get_separator)),
            ]),
            focused_element=input_window,
        )

        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            text = input_buffer.text.strip()
            input_buffer.reset()
            if text and not processing[0]:
                pending_input[0] = text

        @kb.add("c-c")
        @kb.add("c-q")
        def _(event):
            should_exit[0] = True
            event.app.exit()

        style = Style.from_dict({
            "header": "bold fg:green",
            "user": "bold fg:ansiblue",
            "agent": "bold fg:#ff87d7",
            "sep": "#888888",
        })

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            style=style,
            mouse_support=True,
        )

        def make_on_message():
            def on_message(msg):
                if msg.metadata.get("chunk"):
                    if not prefix_printed[0]:
                        chat_fragments.append(
                            ("class:agent", f"{self.config.agent_name}: ")
                        )
                        prefix_printed[0] = True
                    chat_fragments.append(("", msg.content))
                    app.invalidate()
                elif msg.role == "assistant":
                    chat_fragments.append(("", "\n"))
                    prefix_printed[0] = False
                    app.invalidate()
            return on_message

        async def chat_loop():
            nonlocal state

            if first_message:
                chat_fragments.append(
                    ("class:user", f"{self.config.user_name}\uff1a")
                )
                chat_fragments.append(("", f"{first_message}\n"))
                app.invalidate()
                on_msg = make_on_message()
                if self._is_async_provider():
                    state = await self.acreate_state(first_message, on_message=on_msg)
                else:
                    state = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda: self.create_state(first_message, on_message=on_msg),
                    )
                if not self.config.stream:
                    reply = self._last_assistant_message(state)
                    if reply:
                        chat_fragments.append(
                            ("class:agent", f"{self.config.agent_name}: ")
                        )
                        chat_fragments.append(("", f"{reply}\n"))
                        app.invalidate()

            while not should_exit[0]:
                while pending_input[0] is None and not should_exit[0]:
                    await asyncio.sleep(0.05)
                if should_exit[0]:
                    break

                text = pending_input[0]
                pending_input[0] = None

                cmd = text.lower()
                if cmd in {"quit", "exit", ":q", "/exit", "/quit"}:
                    should_exit[0] = True
                    break

                if cmd == "/help":
                    chat_fragments.append(("class:header", "/help\n"))
                    chat_fragments.append(("", "  /exit    Exit the assistant\n"))
                    chat_fragments.append(("", "  /quit    Exit the assistant\n"))
                    chat_fragments.append(("", "  /help    Show this help\n"))
                    chat_fragments.append(("", "\n"))
                    app.invalidate()
                    continue

                processing[0] = True
                chat_fragments.append(
                    ("class:user", f"{self.config.user_name}\uff1a")
                )
                chat_fragments.append(("", f"{text}\n"))
                app.invalidate()

                on_msg = make_on_message()

                if self._is_async_provider():
                    state = await self.acontinue_state(
                        state, text, on_message=on_msg
                    )
                else:
                    def process():
                        return self.continue_state(state, text, on_message=on_msg)

                    state = await asyncio.get_running_loop().run_in_executor(
                        None, process
                    )

                if not self.config.stream:
                    reply = self._last_assistant_message(state)
                    if reply:
                        chat_fragments.append(
                            ("class:agent", f"{self.config.agent_name}: ")
                        )
                        chat_fragments.append(("", f"{reply}\n"))
                        app.invalidate()

                processing[0] = False

            app.exit()

        async def run_app():
            nonlocal state
            app.create_background_task(chat_loop())
            await app.run_async()

        asyncio.run(run_app())
        self._state = state
        print("Goodbye!")
