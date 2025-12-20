import json
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static
from rich.markdown import Markdown as RichMarkdown


# Tool name display mappings for friendlier names
TOOL_DISPLAY_NAMES = {
    "transfer_to_agent": "Delegating to",
    "universal_search": "Searching",
    "web_search": "Searching the web",
    "code_execution": "Running code",
    "file_read": "Reading file",
    "file_write": "Writing file",
}

# Agent name display mappings
AGENT_DISPLAY_NAMES = {
    "prime_agent": "Prime Agent",
    "planning_agent": "Planning Agent",
    "research_agent": "Research Agent",
    "code_executor_agent": "Code Executor",
    "chart_generator_agent": "Chart Generator",
    "mcp_agent": "MCP Agent",
    "generic_executor_agent": "Generic Executor",
    "user_proxy_agent": "User Proxy",
}


class ToolCallWidget(Static):
    """A visually distinct widget for displaying tool calls."""

    DEFAULT_CSS = """
    ToolCallWidget {
        margin: 0 0 1 0;
        padding: 0 1;
        height: auto;
        width: auto;
        border: round $primary-lighten-2;
        background: $surface;
    }

    ToolCallWidget.-running {
        border: round $warning;
    }

    ToolCallWidget.-complete {
        border: round $success-darken-2;
    }

    ToolCallWidget.-transfer {
        border: double $accent;
        background: $surface-darken-1;
    }

    ToolCallWidget .tool-header {
        color: $text;
        text-style: bold;
        width: auto;
        height: auto;
    }
    """

    SPINNER_FRAMES = [".", "..", "...", "....", ".....", "......"]

    def __init__(
        self,
        tool_call_id: str,
        tool_name: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.args: dict = {}
        self.result: str | None = None
        self._is_complete = False
        self._spinner_index = 0

    def compose(self):
        yield Static(self._format_display(), classes="tool-header")

    def on_mount(self) -> None:
        """Start the spinner animation."""
        self.set_interval(0.3, self._advance_spinner)

    def _advance_spinner(self) -> None:
        """Advance the spinner animation."""
        if not self._is_complete:
            self._spinner_index = (self._spinner_index + 1) % len(self.SPINNER_FRAMES)
            self._update_display()

    def _format_display(self) -> str:
        """Format the tool call display text."""
        # Get friendly tool name
        display_name = TOOL_DISPLAY_NAMES.get(self.tool_name, self.tool_name)

        # Build the display string
        parts = []

        # Special handling for transfer_to_agent
        if self.tool_name == "transfer_to_agent":
            agent_name = self.args.get("agent_name", "")
            friendly_agent = AGENT_DISPLAY_NAMES.get(agent_name, agent_name)

            if self._is_complete:
                parts.append(f">> {display_name} {friendly_agent}")
            else:
                spinner = self.SPINNER_FRAMES[self._spinner_index]
                parts.append(f">> {display_name} {friendly_agent} {spinner}")
        else:
            # Generic tool display
            if self._is_complete:
                parts.append(f"[*] {display_name}")
            else:
                spinner = self.SPINNER_FRAMES[self._spinner_index]
                parts.append(f"[~] {display_name} {spinner}")

            # Add relevant args as detail
            detail = self._format_args_detail()
            if detail:
                parts.append(f"    {detail}")

        return "\n".join(parts)

    def _format_args_detail(self) -> str:
        """Format tool arguments as a detail string."""
        if not self.args:
            return ""

        # Extract meaningful details based on tool type
        if "query" in self.args:
            return f'"{self.args["query"]}"'
        elif "path" in self.args:
            return f'"{self.args["path"]}"'
        elif "code" in self.args:
            code = self.args["code"]
            # Truncate long code
            if len(code) > 50:
                code = code[:47] + "..."
            return f'"{code}"'

        return ""

    def _update_display(self) -> None:
        """Update the display text."""
        header = self.query_one(".tool-header", Static)
        header.update(self._format_display())

    def set_args(self, args_json: str) -> None:
        """Set the tool call arguments from JSON string."""
        try:
            self.args = json.loads(args_json)
        except json.JSONDecodeError:
            self.args = {"raw": args_json}

        # Update classes based on tool type
        if self.tool_name == "transfer_to_agent":
            self.add_class("-transfer")

        self._update_display()

    def append_args(self, args_delta: str) -> None:
        """Append to arguments (for streaming args)."""
        # For now, just try to parse the accumulated args
        try:
            self.args = json.loads(args_delta)
            if self.tool_name == "transfer_to_agent":
                self.add_class("-transfer")
            self._update_display()
        except json.JSONDecodeError:
            pass

    def mark_complete(self, result: str | None = None) -> None:
        """Mark the tool call as complete."""
        self._is_complete = True
        self.result = result
        self.remove_class("-running")
        self.add_class("-complete")
        self._update_display()


class StreamingMarkdown(Static):
    """A widget that streams as plain text, then renders as Markdown when complete.

    During streaming, content is displayed as plain text for performance.
    When streaming ends, the full content is rendered as formatted markdown.
    """

    DEFAULT_CSS = """
    StreamingMarkdown {
        border: round $panel;
        padding: 1;
        margin-bottom: 1;
    }
    StreamingMarkdown.-streaming {
        border: round $accent;
    }
    """

    def __init__(self, content: str = "", *, streaming: bool = False, **kwargs) -> None:
        # If not streaming, render as markdown immediately; otherwise plain text
        if streaming:
            super().__init__(content, **kwargs)
        else:
            super().__init__(RichMarkdown(content) if content else "", **kwargs)
        self._content = content
        self._is_streaming = streaming

    def append_content(self, delta: str) -> None:
        """Append text to the content (plain text during streaming)."""
        self._content += delta
        # Fast plain text update during streaming - no markdown parsing
        self.update(self._content)

    def set_streaming(self, is_streaming: bool) -> None:
        """Set the streaming state. When streaming ends, render as markdown."""
        was_streaming = self._is_streaming
        self._is_streaming = is_streaming
        self.set_class(is_streaming, "-streaming")

        # When streaming ends, render the final content as markdown
        if was_streaming and not is_streaming:
            self.update(RichMarkdown(self._content))

    @property
    def content(self) -> str:
        """Get the current content."""
        return self._content


class MessageList(VerticalScroll):
    """Container for chat messages with streaming support."""

    DEFAULT_CSS = """
    MessageList { height: 1fr; padding: 1; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._active_message: StreamingMarkdown | None = None
        self._message_widgets: dict[str, StreamingMarkdown] = {}
        self._tool_widgets: dict[str, ToolCallWidget] = {}

    def on_mount(self) -> None:
        # Pin to bottom as new content is added until user scrolls up.
        self.anchor(True)

    def add(self, md: str, message_id: str | None = None) -> StreamingMarkdown:
        """
        Add a new message to the list.

        Args:
            md: Markdown content for the message
            message_id: Optional ID for tracking streaming messages

        Returns:
            The created StreamingMarkdown widget
        """
        widget = StreamingMarkdown(md)
        if message_id:
            self._message_widgets[message_id] = widget
        self.mount(widget)
        return widget

    def start_streaming_message(
        self, role: str, message_id: str
    ) -> StreamingMarkdown:
        """
        Start a new streaming message.

        Args:
            role: The role (e.g., "assistant", "user")
            message_id: Unique ID for the message

        Returns:
            The created StreamingMarkdown widget
        """
        prefix = f"**{role.title()}**\n\n"
        widget = StreamingMarkdown(prefix, streaming=True)
        widget.add_class("-streaming")
        self._message_widgets[message_id] = widget
        self._active_message = widget
        self.mount(widget)
        return widget

    def append_to_message(self, message_id: str, delta: str) -> None:
        """
        Append content to an existing streaming message.

        Args:
            message_id: ID of the message to update
            delta: Text chunk to append
        """
        widget = self._message_widgets.get(message_id)
        if widget:
            widget.append_content(delta)
        elif self._active_message:
            # Fallback to active message if ID not found
            self._active_message.append_content(delta)

    def end_streaming_message(self, message_id: str) -> None:
        """
        Mark a streaming message as complete.

        Args:
            message_id: ID of the message that finished streaming
        """
        widget = self._message_widgets.get(message_id)
        if widget:
            widget.set_streaming(False)
        if self._active_message and self._active_message == widget:
            self._active_message = None

    def add_user_message(self, text: str) -> StreamingMarkdown:
        """Add a user message."""
        return self.add(f"**You**\n\n{text}")

    def add_system_message(self, text: str) -> StreamingMarkdown:
        """Add a system/status message."""
        return self.add(f"*{text}*")

    def add_tool_call_indicator(self, tool_name: str) -> StreamingMarkdown:
        """Add an indicator that a tool is being called (legacy method)."""
        return self.add(f"> Calling tool: `{tool_name}`...")

    def start_tool_call(
        self, tool_call_id: str, tool_name: str
    ) -> ToolCallWidget:
        """
        Start a new tool call with visual indicator.

        Args:
            tool_call_id: Unique ID for the tool call
            tool_name: Name of the tool being called

        Returns:
            The created ToolCallWidget
        """
        widget = ToolCallWidget(tool_call_id=tool_call_id, tool_name=tool_name)
        widget.add_class("-running")
        self._tool_widgets[tool_call_id] = widget
        self.mount(widget)
        return widget

    def update_tool_call_args(self, tool_call_id: str, args_delta: str) -> None:
        """
        Update the arguments for a tool call.

        Args:
            tool_call_id: ID of the tool call to update
            args_delta: Arguments delta (JSON string)
        """
        widget = self._tool_widgets.get(tool_call_id)
        if widget:
            widget.append_args(args_delta)

    def complete_tool_call(
        self, tool_call_id: str, result: str | None = None
    ) -> None:
        """
        Mark a tool call as complete.

        Args:
            tool_call_id: ID of the tool call that completed
            result: Optional result string
        """
        widget = self._tool_widgets.get(tool_call_id)
        if widget:
            widget.mark_complete(result)