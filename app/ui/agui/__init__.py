"""
AG-UI Protocol client for Textual UI.

This module provides types and utilities for consuming AG-UI protocol
Server-Sent Events (SSE) streams from an AG-UI compatible backend.
"""

from .types import (
    EventType,
    BaseEvent,
    RunStartedEvent,
    RunFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    StepStartedEvent,
    StepFinishedEvent,
    RawEvent,
    parse_event,
)
from .client import AGUIStreamClient

__all__ = [
    "EventType",
    "BaseEvent",
    "RunStartedEvent",
    "RunFinishedEvent",
    "TextMessageStartEvent",
    "TextMessageContentEvent",
    "TextMessageEndEvent",
    "ToolCallStartEvent",
    "ToolCallArgsEvent",
    "ToolCallEndEvent",
    "ToolCallResultEvent",
    "StepStartedEvent",
    "StepFinishedEvent",
    "RawEvent",
    "parse_event",
    "AGUIStreamClient",
]
