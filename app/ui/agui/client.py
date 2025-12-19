"""
AG-UI Protocol streaming client using httpx.

This module provides an async client for consuming AG-UI protocol
Server-Sent Events (SSE) streams from an AG-UI compatible backend.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import httpx

from .types import BaseEvent, EventType, parse_event


@dataclass
class AGUIStreamClient:
    """
    Async client for streaming AG-UI protocol events via SSE.

    Usage:
        client = AGUIStreamClient(base_url="http://localhost:8000")
        async for event in client.stream_run("Hello, agent!"):
            if event.type == EventType.TEXT_MESSAGE_CONTENT:
                print(event.delta, end="", flush=True)
    """

    base_url: str = "http://localhost:8000"
    endpoint: str = "/api/agent"
    timeout: float = 300.0  # 5 minutes for long-running agent tasks
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    async def stream_run(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Stream AG-UI events for a single agent run.

        Args:
            message: The user message to send to the agent
            thread_id: Optional thread ID for conversation continuity
            run_id: Optional run ID

        Yields:
            Parsed AG-UI events
        """
        url = f"{self.base_url}{self.endpoint}"
        tid = thread_id or self.thread_id
        rid = run_id or str(uuid.uuid4())

        # AG-UI RunAgentInput payload (all required fields)
        payload = {
            "threadId": tid,
            "runId": rid,
            "state": {},  # Required: agent state (empty for new conversations)
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "user",
                    "content": message,
                }
            ],
            "tools": [],  # Required: available tools (empty = use server defaults)
            "context": [],  # Required: additional context
            "forwardedProps": {},  # Required: props forwarded to agent
        }

        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for event in self._parse_sse_stream(response):
                    yield event

    async def _parse_sse_stream(
        self, response: httpx.Response
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Parse Server-Sent Events from an httpx streaming response.

        SSE format:
            event: <event-type>  (optional)
            data: <json-data>
            <blank line>

        Args:
            response: The httpx streaming response

        Yields:
            Parsed AG-UI events
        """
        buffer = ""

        async for chunk in response.aiter_text():
            buffer += chunk

            # Process complete SSE messages (separated by double newlines)
            while "\n\n" in buffer:
                message, buffer = buffer.split("\n\n", 1)
                event = self._parse_sse_message(message)
                if event is not None:
                    yield event

        # Process any remaining data in buffer
        if buffer.strip():
            event = self._parse_sse_message(buffer)
            if event is not None:
                yield event

    def _parse_sse_message(self, message: str) -> BaseEvent | None:
        """
        Parse a single SSE message into an AG-UI event.

        Args:
            message: Raw SSE message string

        Returns:
            Parsed event or None if not a data line
        """
        data_content = None

        for line in message.split("\n"):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith(":"):
                continue

            # Handle data lines
            if line.startswith("data:"):
                data_str = line[5:].strip()

                # Handle [DONE] signal
                if data_str == "[DONE]":
                    return None

                try:
                    data_content = json.loads(data_str)
                except json.JSONDecodeError:
                    # Not valid JSON, skip
                    continue

        if data_content is not None:
            return parse_event(data_content)

        return None


@dataclass
class ConversationState:
    """
    Tracks the state of a streaming conversation.

    This helps maintain context across multiple TEXT_MESSAGE events
    and tool calls within a single run.
    """

    messages: dict[str, str] = field(default_factory=dict)
    tool_calls: dict[str, dict] = field(default_factory=dict)
    current_message_id: str | None = None
    is_running: bool = False

    def handle_event(self, event: BaseEvent) -> str | None:
        """
        Process an event and return any text update to display.

        Args:
            event: The AG-UI event to process

        Returns:
            Text content to display, or None
        """
        if event.type == EventType.RUN_STARTED:
            self.is_running = True
            return None

        elif event.type == EventType.RUN_FINISHED:
            self.is_running = False
            return None

        elif event.type == EventType.TEXT_MESSAGE_START:
            from .types import TextMessageStartEvent

            if isinstance(event, TextMessageStartEvent):
                self.current_message_id = event.message_id
                self.messages[event.message_id] = ""
            return None

        elif event.type == EventType.TEXT_MESSAGE_CONTENT:
            from .types import TextMessageContentEvent

            if isinstance(event, TextMessageContentEvent):
                msg_id = event.message_id
                if msg_id not in self.messages:
                    self.messages[msg_id] = ""
                self.messages[msg_id] += event.delta
                return event.delta
            return None

        elif event.type == EventType.TEXT_MESSAGE_END:
            return None

        elif event.type == EventType.TOOL_CALL_START:
            from .types import ToolCallStartEvent

            if isinstance(event, ToolCallStartEvent):
                self.tool_calls[event.tool_call_id] = {
                    "name": event.tool_call_name,
                    "args": "",
                }
            return None

        elif event.type == EventType.TOOL_CALL_ARGS:
            from .types import ToolCallArgsEvent

            if isinstance(event, ToolCallArgsEvent):
                if event.tool_call_id in self.tool_calls:
                    self.tool_calls[event.tool_call_id]["args"] += event.delta
            return None

        elif event.type == EventType.TOOL_CALL_END:
            return None

        return None

    def get_full_message(self, message_id: str) -> str:
        """Get the full accumulated message for a given ID."""
        return self.messages.get(message_id, "")

    def get_current_message(self) -> str:
        """Get the full content of the current message."""
        if self.current_message_id:
            return self.messages.get(self.current_message_id, "")
        return ""
