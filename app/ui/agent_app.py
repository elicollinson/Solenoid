"""
AG-UI compatible Textual application.

This module provides a terminal-based interface that consumes AG-UI protocol
SSE streams and renders them using Textual widgets with real-time streaming.
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, LoadingIndicator, Static
from textual.binding import Binding
from textual import work, on

from app.ui.message_list import MessageList
from app.ui.chat_input import ChatInput
from app.ui.settings import SettingsScreen
from app.ui.agui import (
    AGUIStreamClient,
    EventType,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    RunStartedEvent,
    RunFinishedEvent,
)


class StatusBar(Static):
    """Status bar showing connection and agent state."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    StatusBar.-connected {
        color: $success;
    }
    StatusBar.-error {
        color: $error;
    }
    """

    def set_status(self, text: str, state: str = "normal") -> None:
        """Update status text and visual state."""
        self.update(text)
        self.remove_class("-connected", "-error")
        if state == "connected":
            self.add_class("-connected")
        elif state == "error":
            self.add_class("-error")


class AgentApp(App):
    """
    AG-UI compatible terminal chat application.

    Connects to an AG-UI backend server and streams agent responses
    in real-time with support for text messages and tool calls.
    """

    TITLE = "AG-UI Agent"
    SUB_TITLE = "Terminal Client"

    CSS = """
    Screen { layout: vertical; }
    #loading { height: 3; content-align: center middle; display: none; }
    #loading.-visible { display: block; }
    ChatInput { height: 6; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
    ]

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        endpoint: str = "/api/agent",
        **kwargs,
    ) -> None:
        """
        Initialize the AG-UI agent app.

        Args:
            base_url: Base URL of the AG-UI backend server
            endpoint: API endpoint path for agent runs
            **kwargs: Additional arguments passed to App
        """
        super().__init__(**kwargs)
        self.base_url = base_url
        self.endpoint = endpoint
        self._client: AGUIStreamClient | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield MessageList(id="feed")
        yield LoadingIndicator(id="loading")
        yield ChatInput(placeholder="Ask the agent...")
        yield StatusBar(f"Ready - {self.base_url}{self.endpoint}", id="status")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the AG-UI client on mount."""
        self._client = AGUIStreamClient(
            base_url=self.base_url,
            endpoint=self.endpoint,
        )
        self.loading_indicator = self.query_one("#loading", LoadingIndicator)
        self._set_loading(False)
        self._update_status("Ready", "normal")

    def on_chat_input_submitted(self, msg: ChatInput.Submitted) -> None:
        """Handle user message submission."""
        feed = self.query_one(MessageList)
        # Show the user message immediately
        feed.add_user_message(msg.text)
        self._set_loading(True)
        self._update_status("Connecting...", "normal")
        # Stream the agent response in a background worker
        self._stream_agent_response(msg.text)

    def on_chat_input_command(self, msg: ChatInput.Command) -> None:
        """Handle slash commands from the chat input."""
        self._handle_command(msg.command, msg.args)

    def _handle_command(self, command: str, args: str) -> None:
        """
        Process a slash command.

        Args:
            command: The command name (without leading /)
            args: Any arguments after the command
        """
        feed = self.query_one(MessageList)

        if command == "settings":
            self._open_settings()
        elif command == "help":
            self._show_help()
        elif command == "clear":
            self.action_clear()
        else:
            feed.add_system_message(f"Unknown command: /{command}")
            feed.add_system_message("Type /help for available commands")

    def _open_settings(self) -> None:
        """Open the settings screen."""
        def on_settings_closed(modified: bool) -> None:
            """Callback when settings screen is dismissed."""
            feed = self.query_one(MessageList)
            if modified:
                feed.add_system_message("Settings updated. Some changes may require a restart.")
            self._update_status("Ready", "normal")

        self.push_screen(SettingsScreen(), on_settings_closed)
        self._update_status("Editing settings...", "normal")

    def _show_help(self) -> None:
        """Show available commands."""
        feed = self.query_one(MessageList)
        help_text = """**Available Commands:**
- `/settings` - Open the settings editor
- `/clear` - Clear the chat history
- `/help` - Show this help message"""
        feed.add_system_message(help_text)

    @work(exclusive=True)
    async def _stream_agent_response(self, user_text: str) -> None:
        """
        Stream AG-UI events and update the UI in real-time.

        This runs as an async worker to keep the UI responsive.
        """
        if not self._client:
            self._set_loading(False)
            self._update_status("Error: Client not initialized", "error")
            return

        feed = self.query_one(MessageList)
        current_message_id: str | None = None

        try:
            async for event in self._client.stream_run(user_text):
                # Handle different event types
                if event.type == EventType.RUN_STARTED:
                    self._update_status("Agent running...", "connected")

                elif event.type == EventType.TEXT_MESSAGE_START:
                    if isinstance(event, TextMessageStartEvent):
                        current_message_id = event.message_id
                        # Start a new streaming message in the UI
                        feed.start_streaming_message(
                            role=event.role,
                            message_id=event.message_id,
                        )

                elif event.type == EventType.TEXT_MESSAGE_CONTENT:
                    if isinstance(event, TextMessageContentEvent):
                        # Append the delta to the current message
                        feed.append_to_message(
                            message_id=event.message_id,
                            delta=event.delta,
                        )

                elif event.type == EventType.TEXT_MESSAGE_END:
                    if isinstance(event, TextMessageEndEvent):
                        # Mark the message as complete
                        feed.end_streaming_message(event.message_id)
                        current_message_id = None

                elif event.type == EventType.TOOL_CALL_START:
                    if isinstance(event, ToolCallStartEvent):
                        # Start a new tool call with visual widget
                        feed.start_tool_call(
                            tool_call_id=event.tool_call_id,
                            tool_name=event.tool_call_name,
                        )
                        self._update_status(
                            f"Running: {event.tool_call_name}", "connected"
                        )

                elif event.type == EventType.TOOL_CALL_ARGS:
                    if isinstance(event, ToolCallArgsEvent):
                        # Update tool call with arguments
                        feed.update_tool_call_args(
                            tool_call_id=event.tool_call_id,
                            args_delta=event.delta,
                        )

                elif event.type == EventType.TOOL_CALL_END:
                    if isinstance(event, ToolCallEndEvent):
                        # Mark tool as complete (result may come later)
                        feed.complete_tool_call(tool_call_id=event.tool_call_id)
                        self._update_status("Agent running...", "connected")

                elif event.type == EventType.TOOL_CALL_RESULT:
                    if isinstance(event, ToolCallResultEvent):
                        # Update tool call with result (already marked complete)
                        feed.complete_tool_call(
                            tool_call_id=event.tool_call_id,
                            result=event.content,
                        )

                elif event.type == EventType.RUN_FINISHED:
                    self._update_status("Ready", "normal")

        except Exception as e:
            # Handle connection errors gracefully
            error_msg = str(e)
            if "Connection refused" in error_msg:
                error_msg = f"Cannot connect to {self.base_url}"
            feed.add_system_message(f"Error: {error_msg}")
            self._update_status(f"Error: {error_msg[:30]}...", "error")

        finally:
            self._set_loading(False)
            # Ensure any streaming message is closed
            if current_message_id:
                feed.end_streaming_message(current_message_id)

    def _set_loading(self, is_loading: bool) -> None:
        """Toggle the loading indicator visibility."""
        indicator = getattr(self, "loading_indicator", None)
        if indicator:
            indicator.set_class(is_loading, "-visible")

    def _update_status(self, text: str, state: str = "normal") -> None:
        """Update the status bar."""
        try:
            status = self.query_one("#status", StatusBar)
            status.set_status(text, state)
        except Exception:
            pass  # Status bar might not be mounted yet

    def action_clear(self) -> None:
        """Clear the message feed."""
        feed = self.query_one(MessageList)
        feed.remove_children()
        self._update_status("Cleared", "normal")
