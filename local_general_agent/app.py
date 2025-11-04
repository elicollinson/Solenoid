"""Primary Textual application for the general-purpose terminal agent."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

from agents import (
    Agent,
    HandoffCallItem,
    HandoffOutputItem,
    ItemHelpers,
    MessageOutputItem,
    RunItemStreamEvent,
    RunResult,
    Runner,
    SQLiteSession,
    ToolCallItem,
    ToolCallOutputItem,
    set_default_openai_client,
)
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from openai import AsyncOpenAI
from openai.types.responses import ResponseTextDeltaEvent
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option
from textual.timer import Timer

from .config import AppConfig, load_config, load_settings_dict, save_config
from .shell_agent import create_shell_agent
from .settings_agent import create_settings_agent
from .theme import DEFAULT_THEME, available_themes, get_theme_path


ActionHandler = Callable[["TerminalApp", "MenuScreen"], None]
LabelFactory = Callable[["TerminalApp"], str]


DEFAULT_AGENT_PROMPT_BODY = (
    "You are a helpful terminal assistant. Answer user questions clearly and concisely. "
    "When a task involves inspecting or editing files or running shell-style commands, call the `shell_agent` tool. "
    "The Settings Manager agent is available both as a handoff target and as the `manage_settings` tool. If the user "
    "asks to view or change application settings—such as theme, context window, or any value stored in the settings "
    "file—you MUST immediately hand off to the Settings Manager or invoke the `manage_settings` tool. Never refuse "
    "settings changes yourself; delegate instead so the Settings Manager can list or update settings using its own "
    "tools."
)
DEFAULT_AGENT_PROMPT = prompt_with_handoff_instructions(DEFAULT_AGENT_PROMPT_BODY)
LOCAL_RESPONSES_URL = os.environ.get("LOCAL_RESPONSES_URL", "http://127.0.0.1:4000/v1")
LOCAL_RESPONSES_API_KEY = os.environ.get("LOCAL_RESPONSES_API_KEY", "not-needed")
SESSION_FILE = Path(__file__).resolve().parent.parent / "local_responses.db"
SESSION_ID = os.environ.get("LOCAL_RESPONSES_SESSION_ID", "terminal-app-session")
SPINNER_FRAMES: tuple[str, ...] = ("|", "/", "-", "\\")
CONTEXT_WINDOW_PRESETS: tuple[int, ...] = (8_192, 16_384, 32_768)


@dataclass
class MenuItem:
    """Single selectable menu entry."""

    id: str
    label: str | LabelFactory
    action: ActionHandler | None = None
    submenu: "MenuNode | None" = None

    def render_label(self, app: "TerminalApp") -> str:
        """Resolve the display label for the current application state."""
        return self.label(app) if callable(self.label) else self.label


@dataclass
class MenuNode:
    """Hierarchical menu definition."""

    title: str
    items: list[MenuItem]


@dataclass(slots=True)
class StreamingState:
    """Holds state for an in-flight streamed assistant response."""

    widget: Widget
    message_index: int
    text_parts: list[str] = field(default_factory=list)
    spinner_index: int = 0
    spinner_timer: Timer | None = None

    def append(self, delta: str) -> None:
        if not delta:
            return
        self.text_parts.append(delta)

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


class MenuScreen(Screen):
    """Interactive menu screen supporting nested navigation."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, node: MenuNode, name: str | None = None):
        super().__init__(name=name)
        self.node = node
        self._items = {item.id: item for item in node.items}

    def compose(self) -> ComposeResult:
        yield Static(self.node.title, classes="menu-title")
        yield Static(
            "Use ↑/↓ to navigate, Enter/Space to select, Esc to return.",
            classes="menu-instructions",
        )
        yield OptionList(*self._build_options(), id="menu-options")

    def _build_options(self) -> list[Option]:
        return [Option(item.render_label(self.app), id=item.id) for item in self.node.items]

    def refresh_options(self) -> None:
        """Update option prompts to reflect current state."""
        try:
            option_list = self.query_one(OptionList)
        except Exception:  # Textual raises NoMatches when not mounted yet.
            return

        for item in self.node.items:
            option_list.replace_option_prompt(item.id, item.render_label(self.app))

    def on_show(self) -> None:
        """Refresh prompts when the screen becomes visible."""
        self.refresh_options()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle menu option selection."""
        selected = self._items.get(event.option.id)
        if selected is None:
            return

        if selected.submenu is not None:
            self.app.push_screen(MenuScreen(selected.submenu))
            return

        if selected.action is not None:
            selected.action(self.app, self)
            return

        # Default behaviour for informational menus.
        self.app.add_message("info", f"Selected: {event.option.prompt}")
        self.app.pop_screen()


class TerminalApp(App):
    """A terminal application with Solarized theming and slash commands."""

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+d", "quit", "Quit"),
    ]

    def __init__(self, config: AppConfig | None = None):
        available = set(available_themes())
        self._available_themes = available
        self.config = config or load_config(available)
        self.theme_name = self.config.theme if self.config.theme in available else DEFAULT_THEME
        self.messages: list[tuple[str, str]] = []  # (type, message) pairs
        self._assistant_icon = "<"
        self._user_icon = ">"
        self._spinner_frames = SPINNER_FRAMES
        self._agent_task: asyncio.Task[None] | None = None
        self._agent_client = AsyncOpenAI(base_url=LOCAL_RESPONSES_URL, api_key=LOCAL_RESPONSES_API_KEY)
        set_default_openai_client(self._agent_client)
        workspace_env = os.environ.get("LOCAL_RESPONSES_WORKSPACE_ROOT")
        self._workspace_root = (
            Path(workspace_env).resolve() if workspace_env else Path.cwd().resolve()
        )
        model_id = os.environ.get("LOCAL_RESPONSES_AGENT_MODEL_ID") or os.environ.get(
            "LOCAL_RESPONSES_MODEL_ID"
        )
        agent_model_kwargs: dict[str, Any] = {}
        if model_id:
            agent_model_kwargs["model"] = model_id

        model_override = agent_model_kwargs.get("model")
        self._shell_agent = create_shell_agent(self._workspace_root, model=model_override)
        self._shell_tool = self._shell_agent.as_tool(
            tool_name="shell_agent",
            tool_description=(
                "Use this to safely inspect or edit project files with limited shell-style helpers "
                "(ls, read/write files, search text)."
            ),
        )
        self._settings_agent = create_settings_agent(
            load_settings=load_settings_dict,
            apply_setting=self._apply_setting_change,
            model=model_override,
        )

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._agent_session = SQLiteSession(SESSION_ID, str(SESSION_FILE))

        async def _settings_output_extractor(run_result: RunResult) -> str:
            if isinstance(run_result.final_output, str) and run_result.final_output.strip():
                return run_result.final_output.strip()
            if run_result.final_output not in (None, ""):
                formatted = self._stringify_output(run_result.final_output)
                if formatted.strip():
                    return formatted.strip()
            aggregated = ItemHelpers.text_message_outputs(run_result.new_items)
            if aggregated.strip():
                return aggregated.strip()
            return "Settings updated."

        self._settings_tool = self._settings_agent.as_tool(
            tool_name="manage_settings",
            tool_description=(
                "Inspect or modify application settings such as theme or context window."
            ),
            custom_output_extractor=_settings_output_extractor,
            session=self._agent_session,
        )
        prompt_override = os.environ.get("LOCAL_RESPONSES_PROMPT")
        prompt = (
            prompt_with_handoff_instructions(prompt_override)
            if prompt_override
            else DEFAULT_AGENT_PROMPT
        )
        agent_kwargs = {
            "name": "Local Assistant",
            "instructions": prompt,
            "tools": [self._shell_tool, self._settings_tool],
            "handoffs": [self._settings_agent],
            **agent_model_kwargs,
        }
        self._agent = Agent(**agent_kwargs)
        self._needs_model_warmup = True
        self.context_window_tokens = self.config.context_window_tokens
        self._server_process: subprocess.Popen[bytes] | None = None
        self._server_cwd = Path(__file__).resolve().parent.parent
        self._server_log_path = self._server_cwd / "local_responses.log"
        self._server_log_handle: TextIO | None = None
        super().__init__()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.apply_theme(self.theme_name, persist=False)
        self.query_one(Input).focus()
        self.add_message("info", "Type /commands to see available commands")
        if os.environ.get("LOCAL_RESPONSES_AUTOSTART", "1") != "0":
            asyncio.create_task(self._auto_start_server())

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()
        yield VerticalScroll(
            Static("Terminal App - Solarized Edition\nType /commands for help\n", id="welcome"),
            id="messages",
        )
        yield Input(placeholder="Type a command or message...")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        text = event.value.strip()
        input_widget = self.query_one(Input)
        input_widget.value = ""

        if not text:
            return

        # Check for exit commands
        if text.lower() in ["exit", "quit", "q"]:
            self.add_message("success", "Goodbye!")
            self.exit()
            return

        # Check for slash commands
        if text.startswith("/"):
            self.handle_slash_command(text)
        else:
            self._handle_model_request(text)

    def handle_slash_command(self, text: str) -> None:
        """Handle slash commands."""
        # Remove the slash and split into command and args
        command_parts = text[1:].split()
        if not command_parts:
            self.add_message("error", "Invalid command")
            return

        command = command_parts[0].lower()
        args = command_parts[1:]

        if command == "theme":
            self._handle_theme_command(args)
        elif command == "clear":
            self.clear_messages()
        elif command == "commands":
            self.show_commands()
        elif command == "settings":
            self.open_settings()
        elif command == "help":
            self.show_menu(
                "Help",
                [
                    ("commands", "Commands - View available commands"),
                    ("shortcuts", "Keyboard Shortcuts - View keyboard shortcuts"),
                    ("about", "About - About this application"),
                ],
            )
        elif command == "tools":
            self.show_menu(
                "Tools",
                [
                    ("calculator", "Calculator - Simple calculator tool"),
                    ("converter", "Converter - Unit converter"),
                    ("formatter", "Formatter - Text formatting tools"),
                ],
            )
        else:
            self.add_message("warning", f"Unknown command: /{command}")

    def _handle_model_request(self, prompt: str) -> None:
        """Route plain text input to the local responses service."""
        if self._agent_task and not self._agent_task.done():
            self.add_message("warning", "Assistant is still responding. Please wait for it to finish.")
            return

        if self._needs_model_warmup:
            self.add_message(
                "info",
                "Preparing local model cache — the first reply may take up to a minute while weights download.",
            )

        self.add_message("user", prompt)
        stream_state = self._create_streaming_state()
        self._agent_task = asyncio.create_task(self._run_agent_stream(prompt, stream_state))

    def _create_streaming_state(self) -> StreamingState:
        """Create UI state for a streaming assistant reply."""
        widget = self.add_message("assistant", "")
        state = StreamingState(widget=widget, message_index=len(self.messages) - 1)
        state.spinner_timer = self.set_interval(0.12, lambda: self._advance_spinner(state))
        placeholder = (
            "Downloading and loading the local model — this may take a little longer."
            if self._needs_model_warmup
            else "Generating response..."
        )
        self._render_streaming_state(state, placeholder=placeholder)
        return state

    def _advance_spinner(self, state: StreamingState) -> None:
        """Advance the spinner animation for a streaming response."""
        if state.spinner_timer is None:
            return
        state.spinner_index = (state.spinner_index + 1) % len(self._spinner_frames)
        self._render_streaming_state(state)

    def _render_streaming_state(self, state: StreamingState, placeholder: str = "Generating response...") -> None:
        """Render the streaming message with current text and spinner frame."""
        text = state.text.strip() or placeholder
        icon = self._spinner_frames[state.spinner_index] if state.spinner_timer is not None else self._assistant_icon
        state.widget.update(f"{icon} {text}")
        if 0 <= state.message_index < len(self.messages):
            self.messages[state.message_index] = ("assistant", text)
        self.query_one("#messages", VerticalScroll).scroll_end()

    def _append_stream_text(self, state: StreamingState, delta: str) -> None:
        """Append streamed text to the active assistant message."""
        state.append(delta)
        self._render_streaming_state(state)

    def _stringify_output(self, output: Any) -> str:
        if isinstance(output, str):
            return output
        if output is None:
            return ""
        try:
            return json.dumps(output, indent=2, ensure_ascii=False)
        except TypeError:
            return str(output)

    def _handle_run_item_event(self, event: RunItemStreamEvent, state: StreamingState) -> None:
        """Render higher-level streaming events such as messages, tools, and handoffs."""
        item = event.item
        if isinstance(item, MessageOutputItem):
            text = ItemHelpers.text_message_output(item)
            if text:
                self._append_stream_text(state, text)
            return

        if isinstance(item, ToolCallItem):
            tool_name = getattr(item.raw_item, "name", None) or getattr(item.raw_item, "type", "tool")
            self.add_message("info", f"Calling `{tool_name}`…")
            return

        if isinstance(item, ToolCallOutputItem):
            output_text = self._stringify_output(item.output)
            if output_text:
                raw = item.raw_item
                call_id = None
                if isinstance(raw, dict):
                    call_id = raw.get("call_id")
                else:
                    call_id = getattr(raw, "call_id", None)
                call_label = call_id or "tool"
                self.add_message(
                    "assistant",
                    f"Tool `{call_label}` output:\n```text\n{output_text}\n```",
                )
            return

        if isinstance(item, HandoffCallItem):
            target = getattr(item.raw_item, "name", None) or item.agent.name
            self.add_message("info", f"Handoff requested: {target}")
            return

        if isinstance(item, HandoffOutputItem):
            self.add_message("info", f"Handoff completed: {item.target_agent.name}")
            return

    def _stop_spinner(self, state: StreamingState) -> None:
        """Stop the spinner animation."""
        if state.spinner_timer is None:
            return
        state.spinner_timer.stop()
        state.spinner_timer = None
        state.spinner_index = 0

    def _finalize_stream(self, state: StreamingState, final_text: str | None = None) -> None:
        """Finalize the assistant message once streaming completes."""
        self._stop_spinner(state)
        combined_text = final_text if final_text is not None else state.text
        display_text = combined_text.strip() or "Assistant did not return any text."
        state.widget.update(f"{self._assistant_icon} {display_text}")
        if 0 <= state.message_index < len(self.messages):
            self.messages[state.message_index] = ("assistant", display_text)
        self.query_one("#messages", VerticalScroll).scroll_end()
        self._needs_model_warmup = False

    def _handle_stream_error(self, state: StreamingState, exc: Exception) -> None:
        """Handle errors raised during streaming."""
        self._stop_spinner(state)
        error_text = f"Assistant error: {exc}"
        state.widget.update(f"✗ {error_text}")
        if 0 <= state.message_index < len(self.messages):
            self.messages[state.message_index] = ("error", error_text)

    def _apply_setting_change(self, key: str, value: Any) -> str:
        """Apply a settings update originating from the settings agent."""
        settings = load_settings_dict()
        previous = settings.get(key)

        if key == "theme":
            if not isinstance(value, str):
                raise ValueError("Theme must be a string.")
            if value not in self._available_themes:
                options = ", ".join(sorted(self._available_themes))
                raise ValueError(f"Unknown theme '{value}'. Available options: {options}")
            if previous == value:
                return f"Theme already set to {value!r}."
            self.set_theme(value)
            return f"Theme updated to {value!r}."

        if key == "context_window_tokens":
            if not isinstance(value, int):
                raise ValueError("context_window_tokens must be an integer.")
            if value <= 0:
                raise ValueError("context_window_tokens must be positive.")
            if previous == value:
                return f"context_window_tokens already set to {value}."
            self.set_context_window(value)
            return f"Context window updated to {value} tokens."

        if previous == value:
            return f"Setting '{key}' already set to {value!r}."

        self.config.extras[key] = value
        save_config(self.config)
        status = "Updated" if previous is not None else "Added"
        return f"{status} setting '{key}' to {value!r}."

    async def _run_agent_stream(self, prompt: str, state: StreamingState) -> None:
        """Stream a response from the configured agent into the UI."""
        try:
            result = Runner.run_streamed(
                self._agent,
                input=prompt,
                session=self._agent_session,
            )
            async for event in result.stream_events():
                if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                    self._append_stream_text(state, event.data.delta or "")
                elif isinstance(event, RunItemStreamEvent):
                    self._handle_run_item_event(event, state)
                elif event.type == "agent_updated_stream_event":
                    self.add_message("info", f"Agent switched to {event.new_agent.name}")
            final_text = ""
            if isinstance(result.final_output, str):
                final_text = result.final_output
            elif result.final_output not in (None, ""):
                final_text = self._stringify_output(result.final_output)
            if not final_text.strip():
                final_text = ItemHelpers.text_message_outputs(result.new_items)
            self._finalize_stream(state, final_text=final_text)
        except asyncio.CancelledError:
            self._stop_spinner(state)
            state.widget.update(f"{self._assistant_icon} (cancelled)")
            if 0 <= state.message_index < len(self.messages):
                self.messages[state.message_index] = ("assistant", "(cancelled)")
            raise
        except Exception as exc:  # pragma: no cover - runtime IO
            self._handle_stream_error(state, exc)
        finally:
            self._agent_task = None

    def _handle_theme_command(self, args: Iterable[str]) -> None:
        """Toggle or set the current theme based on command arguments."""
        if not args:
            self.toggle_theme()
            return

        theme = args[0].lower()
        if theme not in self._available_themes:
            options = ", ".join(sorted(self._available_themes))
            self.add_message("error", f"Unknown theme '{theme}'. Available: {options}")
            return

        self.set_theme(theme)

    def set_theme(self, theme: str) -> None:
        """Explicitly set the theme."""
        if theme == self.theme_name:
            self.add_message("info", f"Theme already set to {theme}")
            return

        self.apply_theme(theme)
        self.add_message("success", f"Theme switched to {theme}")

    def toggle_theme(self) -> None:
        """Toggle between available themes."""
        ordered = sorted(self._available_themes)
        try:
            index = ordered.index(self.theme_name)
        except ValueError:
            index = 0
        next_index = (index + 1) % len(ordered)
        next_theme = ordered[next_index]
        self.apply_theme(next_theme)
        self.add_message("success", f"Theme switched to {next_theme}")

    def apply_theme(self, theme: str, persist: bool = True) -> None:
        """Load and apply theme CSS, optionally persisting the choice."""
        css_path = get_theme_path(theme).resolve()
        stylesheet = self.stylesheet
        theme_sources = {
            str(get_theme_path(name).resolve()) for name in self._available_themes
        }
        for key in list(stylesheet.source.keys()):
            source_path, _ = key
            if source_path in theme_sources:
                stylesheet.source.pop(key, None)

        stylesheet.read(css_path)
        self.refresh_css()
        self.theme_name = theme
        self.dark = theme == "dark"

        if persist:
            self.config.theme = theme
            save_config(self.config)

    def _format_context_window(self, tokens: int) -> str:
        if tokens >= 1024:
            return f"{tokens // 1024}k tokens"
        return f"{tokens} tokens"

    def set_context_window(self, tokens: int) -> None:
        """Persist a new context window preference."""
        if tokens == self.context_window_tokens:
            self.add_message("info", f"Context window already set to {self._format_context_window(tokens)}.")
            return

        self.context_window_tokens = tokens
        self.config.context_window_tokens = tokens
        save_config(self.config)
        self.add_message("success", f"Context window preference set to {self._format_context_window(tokens)}.")
        if self.is_server_running():
            self.add_message("info", "Restarting local responses service to apply the new context window…")
            self.restart_responses_server()
        else:
            self.add_message(
                "warning",
                "Local responses service is not running; start it to apply the new context window.",
            )

    def _build_server_command(self) -> list[str]:
        """Assemble the command used to launch the local responses service."""
        runner = os.environ.get("LOCAL_RESPONSES_RUNNER", "uv")
        model = os.environ.get("LOCAL_RESPONSES_MODEL", "mlx_granite")
        model_id = os.environ.get("LOCAL_RESPONSES_MODEL_ID", "mlx_granite_4.0_h_tiny_4bit")
        port = os.environ.get("LOCAL_RESPONSES_PORT", "4000")
        extra_args = shlex.split(os.environ.get("LOCAL_RESPONSES_EXTRA_ARGS", ""))
        cmd = [
            runner,
            "run",
            "python",
            "-m",
            "local_responses",
            "--model",
            model,
            "--model-id",
            model_id,
            "--port",
            port,
            "--context-window",
            str(self.context_window_tokens),
        ]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    def _close_log_handle(self) -> None:
        """Close the server log file handle if one is open."""
        handle = self._server_log_handle
        if handle is None:
            return
        try:
            handle.flush()
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            handle.close()
        except Exception:  # pragma: no cover - defensive
            pass
        self._server_log_handle = None

    def is_server_running(self) -> bool:
        """Return True if the local responses server subprocess is running."""
        process = self._server_process
        if process is None:
            return False
        if process.poll() is None:
            return True
        # Process has exited; clean up.
        self._server_process = None
        self._close_log_handle()
        return False

    def start_responses_server(self, announce: bool = True) -> None:
        """Start the local responses service if it isn't already running."""
        if self.is_server_running():
            if announce:
                self.add_message("info", "Local responses service is already running.")
            return

        command = self._build_server_command()
        try:
            # Ensure any previous handle is closed before opening anew.
            self._close_log_handle()
            self._server_log_handle = self._server_log_path.open(
                "a", encoding="utf-8", buffering=1
            )
            self._server_process = subprocess.Popen(
                command,
                cwd=str(self._server_cwd),
                stdout=self._server_log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            self._server_process = None
            self._close_log_handle()
            self.add_message("error", f"Failed to start responses service: {exc}")
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._server_process = None
            self._close_log_handle()
            self.add_message("error", f"Unexpected error starting responses service: {exc}")
            return

        if announce:
            joined = " ".join(shlex.quote(part) for part in command)
            self.add_message(
                "success",
                (
                    f"Started local responses service (pid {self._server_process.pid}) with `{joined}`.\n"
                    f"Logs → {self._server_log_path}"
                ),
            )

    def _terminate_process(self, process: subprocess.Popen[bytes]) -> None:
        """Gracefully terminate the provided subprocess."""
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - extreme case
                pass

    def stop_responses_server(self, announce: bool = True) -> None:
        """Stop the local responses service if it is running."""
        process = self._server_process
        if process is None or process.poll() is not None:
            self._server_process = None
            if announce:
                self.add_message("info", "Local responses service is not running.")
            return

        self._terminate_process(process)
        self._server_process = None
        self._close_log_handle()
        if announce:
            self.add_message("success", "Stopped local responses service.")

    def restart_responses_server(self, announce: bool = True) -> None:
        """Restart the local responses service."""
        was_running = self.is_server_running()
        self.stop_responses_server(announce=announce and was_running)
        self.start_responses_server(announce=announce)

    async def _auto_start_server(self) -> None:
        """Auto-start the local responses service once the app loop is running."""
        await asyncio.sleep(0.1)
        self.start_responses_server(announce=False)

    def clear_messages(self) -> None:
        """Clear all messages."""
        messages_widget = self.query_one("#messages", VerticalScroll)
        messages_widget.remove_children()
        messages_widget.mount(
            Static("Terminal App - Solarized Edition\nType /commands for help\n", id="welcome")
        )
        self.messages.clear()
        self.add_message("info", "Messages cleared")

    def show_commands(self) -> None:
        """Show available commands."""
        available = ", ".join(sorted(self._available_themes))
        help_text = f"""
Available Commands:

Built-in Commands:
  /theme [name]  - Toggle theme or switch to a specific theme ({available})
  /clear         - Clear messages
  /commands      - List all commands

Menu Commands:
  /settings      - Configure application settings
  /help          - Get help and view documentation
  /tools         - Access various tools

Exit Commands:
  exit, quit, q  - Exit the application

Settings Navigation:
  Use arrow keys to move, Enter/Space to change, Esc to go back
        """
        self.add_message("info", help_text)

    def open_settings(self) -> None:
        """Launch the hierarchical settings menu."""
        self.push_screen(MenuScreen(self._create_settings_menu()))

    def show_menu(self, title: str, options: Iterable[tuple[str, str]]) -> None:
        """Show a simple informational menu."""

        def make_action(label: str) -> ActionHandler:
            def action(app: "TerminalApp", screen: MenuScreen, label: str = label) -> None:
                app.add_message("info", f"Selected: {label}")
                app.pop_screen()

            return action

        menu_items = [
            MenuItem(id=key, label=label, action=make_action(label)) for key, label in options
        ]
        node = MenuNode(title, menu_items)
        self.push_screen(MenuScreen(node))

    def _create_settings_menu(self) -> MenuNode:
        """Build the menu tree for settings."""

        def make_theme_label(theme: str, display: str) -> LabelFactory:
            def label(app: "TerminalApp") -> str:
                marker = "✓" if app.theme_name == theme else " "
                return f"{marker} {display}"

            return label

        def make_theme_action(theme: str) -> ActionHandler:
            def action(app: "TerminalApp", screen: MenuScreen) -> None:
                app.set_theme(theme)
                screen.refresh_options()

            return action

        def make_context_label(tokens: int) -> LabelFactory:
            def label(app: "TerminalApp") -> str:
                marker = "✓" if getattr(app, "context_window_tokens", 0) == tokens else " "
                return f"{marker} {app._format_context_window(tokens)}"

            return label

        def make_context_action(tokens: int) -> ActionHandler:
            def action(app: "TerminalApp", screen: MenuScreen) -> None:
                app.set_context_window(tokens)
                screen.refresh_options()

            return action

        def server_summary(app: "TerminalApp") -> str:
            return f"Responses Server ({'running' if app.is_server_running() else 'stopped'})"

        def make_server_action(kind: str) -> ActionHandler:
            def action(app: "TerminalApp", screen: MenuScreen) -> None:
                if kind == "start":
                    app.start_responses_server()
                elif kind == "stop":
                    app.stop_responses_server()
                elif kind == "restart":
                    app.restart_responses_server()
                screen.refresh_options()

            return action

        theme_items = [
            MenuItem(
                id=f"settings:theme:{theme}",
                label=make_theme_label(theme, theme.replace("_", " ").title()),
                action=make_theme_action(theme),
            )
            for theme in sorted(self._available_themes)
        ]

        context_items = [
            MenuItem(
                id=f"settings:context:{tokens}",
                label=make_context_label(tokens),
                action=make_context_action(tokens),
            )
            for tokens in CONTEXT_WINDOW_PRESETS
        ]

        theme_menu = MenuNode(
            title="Theme Settings",
            items=theme_items,
        )

        context_menu = MenuNode(
            title="Context Window",
            items=context_items,
        )

        server_menu = MenuNode(
            title="Responses Server Controls",
            items=[
                MenuItem(
                    id="settings:server:start",
                    label="Start Service",
                    action=make_server_action("start"),
                ),
                MenuItem(
                    id="settings:server:stop",
                    label="Stop Service",
                    action=make_server_action("stop"),
                ),
                MenuItem(
                    id="settings:server:restart",
                    label="Restart Service",
                    action=make_server_action("restart"),
                ),
            ],
        )

        def context_summary(app: "TerminalApp") -> str:
            return f"Context Window ({app._format_context_window(app.context_window_tokens)})"

        return MenuNode(
            title="Settings",
            items=[
                MenuItem(
                    id="settings:theme",
                    label="Theme",
                    submenu=theme_menu,
                ),
                MenuItem(
                    id="settings:context",
                    label=context_summary,
                    submenu=context_menu,
                ),
                MenuItem(
                    id="settings:server",
                    label=server_summary,
                    submenu=server_menu,
                ),
            ],
        )

    def add_message(self, msg_type: str, message: str) -> Widget:
        """Add a message to the messages area."""
        icons = {
            "success": "✓",
            "error": "✗",
            "warning": "⚠",
            "info": "ℹ",
            "assistant": getattr(self, "_assistant_icon", "<"),
            "user": getattr(self, "_user_icon", ">"),
        }
        icon = icons.get(msg_type, "•")

        text = f"{icon} {message}"
        if msg_type == "assistant":
            widget: Widget = Markdown(text, classes=msg_type)
        else:
            widget = Static(text, classes=msg_type)
        messages_widget = self.query_one("#messages", VerticalScroll)
        messages_widget.mount(widget)
        messages_widget.scroll_end()
        self.messages.append((msg_type, message))
        return widget

    def action_quit(self) -> None:
        """Quit the application."""
        self.stop_responses_server(announce=False)
        self.exit()


def run_app(theme: str | None = None) -> None:
    """Entry point for external callers."""
    available = set(available_themes())
    config = load_config(available)
    if theme and theme in available:
        config.theme = theme
    app = TerminalApp(config=config)
    app.run()
