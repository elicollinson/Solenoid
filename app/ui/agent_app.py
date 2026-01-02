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
from app.ui.create_agent import CreateAgentScreen
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

    TITLE = "Solenoid"
    SUB_TITLE = ""

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
        elif command == "reload-agents":
            self._reload_agents()
        elif command == "agents":
            self._list_agents()
        elif command == "kb-stats":
            self._show_kb_stats(args)
        elif command == "kb-clear":
            self._clear_kb(args)
        elif command == "create-agent":
            self._open_create_agent()
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

**General:**
- `/settings` - Open the settings editor
- `/clear` - Clear the chat history
- `/help` - Show this help message

**Agent Management:**
- `/create-agent` - Create a new custom agent (agentic workflow)
  The model will plan, research sources, and build the KB with your approval
- `/agents` - List all available agents
- `/reload-agents` - Reload custom agents from agents/ directory

**Knowledge Base:**
- `/kb-stats <agent>` - Show KB statistics for an agent
- `/kb-clear <agent>` - Clear all KB data for an agent"""
        feed.add_system_message(help_text)

    def _open_create_agent(self) -> None:
        """Open the agent creation wizard."""
        def on_wizard_closed(created: bool) -> None:
            """Callback when wizard is dismissed."""
            feed = self.query_one(MessageList)
            if created:
                feed.add_system_message("Custom agent created successfully! Use `/agents` to see all agents.")
            self._update_status("Ready", "normal")

        self.push_screen(CreateAgentScreen(), on_wizard_closed)
        self._update_status("Creating agent...", "normal")

    @work(exclusive=False)
    async def _reload_agents(self) -> None:
        """Reload custom agents from the agents/ directory."""
        import httpx

        feed = self.query_one(MessageList)
        feed.add_system_message("Reloading custom agents...")
        self._update_status("Reloading agents...", "normal")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/reload-agents",
                    timeout=30.0,
                )
                data = response.json()

            if data.get("status") == "success":
                agent_count = data.get("agents_loaded", 0)
                agent_names = data.get("agent_names", [])
                errors = data.get("errors", [])

                if agent_count > 0:
                    names_str = ", ".join(agent_names)
                    feed.add_system_message(
                        f"Loaded {agent_count} custom agent(s): {names_str}"
                    )
                else:
                    feed.add_system_message("No custom agents found in agents/ directory")

                if errors:
                    for error in errors:
                        feed.add_system_message(f"Error: {error}")

                self._update_status("Ready", "normal")
            else:
                error_msg = data.get("message", "Unknown error")
                feed.add_system_message(f"Reload failed: {error_msg}")
                self._update_status("Reload failed", "error")

        except Exception as e:
            feed.add_system_message(f"Failed to reload agents: {e}")
            self._update_status("Error", "error")

    @work(exclusive=False)
    async def _list_agents(self) -> None:
        """List all available agents."""
        import httpx

        feed = self.query_one(MessageList)
        self._update_status("Fetching agents...", "normal")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/agents",
                    timeout=10.0,
                )
                data = response.json()

            builtin = data.get("builtin_agents", [])
            custom = data.get("custom_agents", [])

            lines = ["**Available Agents:**", "", "**Built-in:**"]
            for agent in builtin:
                lines.append(f"- `{agent['name']}`: {agent['description']}")

            if custom:
                lines.append("")
                lines.append("**Custom:**")
                for agent in custom:
                    status = "enabled" if agent.get("enabled", True) else "disabled"
                    kb_status = "KB enabled" if agent.get("has_kb", False) else ""
                    extra = f" [{status}]" if status == "disabled" else ""
                    if kb_status:
                        extra += f" [{kb_status}]"
                    lines.append(f"- `{agent['name']}`: {agent['description']}{extra}")
            else:
                lines.append("")
                lines.append("*No custom agents. Add YAML files to agents/ directory.*")

            feed.add_system_message("\n".join(lines))
            self._update_status("Ready", "normal")

        except Exception as e:
            feed.add_system_message(f"Failed to list agents: {e}")
            self._update_status("Error", "error")

    @work(exclusive=False)
    async def _show_kb_stats(self, agent_name: str) -> None:
        """Show knowledge base statistics for an agent."""
        import httpx

        feed = self.query_one(MessageList)

        if not agent_name.strip():
            feed.add_system_message("Usage: /kb-stats <agent_name>")
            return

        agent_name = agent_name.strip()
        self._update_status(f"Fetching KB stats for {agent_name}...", "normal")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/kb/{agent_name}/stats",
                    timeout=10.0,
                )
                data = response.json()

            if data.get("status") == "success":
                stats_text = f"""**Knowledge Base Stats for `{agent_name}`:**
- Chunks: {data.get('chunk_count', 0)}
- Documents: {data.get('doc_count', 0)}
- Total text: {data.get('total_text_length', 0):,} characters
- Embeddings: {data.get('embedding_count', 0)}"""
                feed.add_system_message(stats_text)
            else:
                feed.add_system_message(f"Error: {data.get('message', 'Unknown error')}")

            self._update_status("Ready", "normal")

        except Exception as e:
            feed.add_system_message(f"Failed to get KB stats: {e}")
            self._update_status("Error", "error")

    @work(exclusive=False)
    async def _clear_kb(self, agent_name: str) -> None:
        """Clear knowledge base for an agent."""
        import httpx

        feed = self.query_one(MessageList)

        if not agent_name.strip():
            feed.add_system_message("Usage: /kb-clear <agent_name>")
            return

        agent_name = agent_name.strip()

        # Show confirmation
        feed.add_system_message(
            f"Clearing KB for `{agent_name}`... "
            "(To cancel, this would need a confirmation modal - proceeding)"
        )
        self._update_status(f"Clearing KB for {agent_name}...", "normal")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/kb/{agent_name}/clear",
                    timeout=30.0,
                )
                data = response.json()

            if data.get("status") == "success":
                count = data.get("chunks_deleted", 0)
                feed.add_system_message(
                    f"Cleared KB for `{agent_name}`: {count} chunks deleted"
                )
            else:
                feed.add_system_message(f"Error: {data.get('message', 'Unknown error')}")

            self._update_status("Ready", "normal")

        except Exception as e:
            feed.add_system_message(f"Failed to clear KB: {e}")
            self._update_status("Error", "error")

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
