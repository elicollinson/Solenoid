"""
AG-UI Protocol event types.

This module defines the event types used by the AG-UI protocol for
streaming agent responses to UI clients via Server-Sent Events (SSE).

Reference: https://docs.ag-ui.com/concepts/messages
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """AG-UI protocol event types."""

    # Lifecycle events
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"

    # Step events
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"

    # Text message events (streaming pattern: START -> CONTENT* -> END)
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"

    # Tool call events (streaming pattern: START -> ARGS* -> END -> RESULT)
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    # State synchronization events
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"

    # Raw/custom events
    RAW = "RAW"
    CUSTOM = "CUSTOM"


@dataclass
class BaseEvent:
    """Base class for all AG-UI events."""
    type: EventType
    raw_data: dict[str, Any] | None = None


@dataclass
class RunStartedEvent(BaseEvent):
    """Emitted when an agent run begins."""
    thread_id: str | None = None
    run_id: str | None = None


@dataclass
class RunFinishedEvent(BaseEvent):
    """Emitted when an agent run completes."""
    thread_id: str | None = None
    run_id: str | None = None


@dataclass
class StepStartedEvent(BaseEvent):
    """Emitted when a step within a run begins."""
    step_name: str | None = None


@dataclass
class StepFinishedEvent(BaseEvent):
    """Emitted when a step within a run completes."""
    step_name: str | None = None


@dataclass
class TextMessageStartEvent(BaseEvent):
    """Signals the start of a new text message."""
    message_id: str = ""
    role: str = "assistant"  # "user", "assistant", "system", "tool", etc.


@dataclass
class TextMessageContentEvent(BaseEvent):
    """Carries a chunk of text content for streaming."""
    message_id: str = ""
    delta: str = ""  # Text chunk to append


@dataclass
class TextMessageEndEvent(BaseEvent):
    """Signals the end of a text message."""
    message_id: str = ""


@dataclass
class ToolCallStartEvent(BaseEvent):
    """Signals the start of a tool call."""
    tool_call_id: str = ""
    tool_call_name: str = ""
    parent_message_id: str | None = None


@dataclass
class ToolCallArgsEvent(BaseEvent):
    """Carries a chunk of tool call arguments."""
    tool_call_id: str = ""
    delta: str = ""  # JSON fragment to append


@dataclass
class ToolCallEndEvent(BaseEvent):
    """Signals the end of a tool call."""
    tool_call_id: str = ""


@dataclass
class ToolCallResultEvent(BaseEvent):
    """Contains the result of a tool call."""
    tool_call_id: str = ""
    message_id: str = ""
    content: str = ""  # JSON string of the result


@dataclass
class RawEvent(BaseEvent):
    """Raw event for unhandled or custom event types."""
    data: dict[str, Any] | None = None


def parse_event(data: dict[str, Any]) -> BaseEvent:
    """
    Parse a raw JSON event dict into a typed AG-UI event.

    Args:
        data: Raw JSON dict from the SSE stream

    Returns:
        Typed event object
    """
    event_type_str = data.get("type", "")

    try:
        event_type = EventType(event_type_str)
    except ValueError:
        # Unknown event type - return as raw
        return RawEvent(type=EventType.RAW, raw_data=data, data=data)

    # Parse based on event type
    if event_type == EventType.RUN_STARTED:
        return RunStartedEvent(
            type=event_type,
            raw_data=data,
            thread_id=data.get("threadId"),
            run_id=data.get("runId"),
        )

    elif event_type == EventType.RUN_FINISHED:
        return RunFinishedEvent(
            type=event_type,
            raw_data=data,
            thread_id=data.get("threadId"),
            run_id=data.get("runId"),
        )

    elif event_type == EventType.STEP_STARTED:
        return StepStartedEvent(
            type=event_type,
            raw_data=data,
            step_name=data.get("stepName"),
        )

    elif event_type == EventType.STEP_FINISHED:
        return StepFinishedEvent(
            type=event_type,
            raw_data=data,
            step_name=data.get("stepName"),
        )

    elif event_type == EventType.TEXT_MESSAGE_START:
        return TextMessageStartEvent(
            type=event_type,
            raw_data=data,
            message_id=data.get("messageId", ""),
            role=data.get("role", "assistant"),
        )

    elif event_type == EventType.TEXT_MESSAGE_CONTENT:
        return TextMessageContentEvent(
            type=event_type,
            raw_data=data,
            message_id=data.get("messageId", ""),
            delta=data.get("delta", ""),
        )

    elif event_type == EventType.TEXT_MESSAGE_END:
        return TextMessageEndEvent(
            type=event_type,
            raw_data=data,
            message_id=data.get("messageId", ""),
        )

    elif event_type == EventType.TOOL_CALL_START:
        return ToolCallStartEvent(
            type=event_type,
            raw_data=data,
            tool_call_id=data.get("toolCallId", ""),
            tool_call_name=data.get("toolCallName", ""),
            parent_message_id=data.get("parentMessageId"),
        )

    elif event_type == EventType.TOOL_CALL_ARGS:
        return ToolCallArgsEvent(
            type=event_type,
            raw_data=data,
            tool_call_id=data.get("toolCallId", ""),
            delta=data.get("delta", ""),
        )

    elif event_type == EventType.TOOL_CALL_END:
        return ToolCallEndEvent(
            type=event_type,
            raw_data=data,
            tool_call_id=data.get("toolCallId", ""),
        )

    elif event_type == EventType.TOOL_CALL_RESULT:
        return ToolCallResultEvent(
            type=event_type,
            raw_data=data,
            tool_call_id=data.get("toolCallId", ""),
            message_id=data.get("messageId", ""),
            content=data.get("content", ""),
        )

    else:
        # Return as raw event for any other types
        return RawEvent(type=event_type, raw_data=data, data=data)
