"""Helpers for building OpenAI Responses payloads and SSE events."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import orjson

from .schemas import (
    ResponseFunctionCall,
    ResponseOutputMessage,
    ResponsePayload,
    ResponseUsage,
)
from .tool_parsing import ToolCall


def _now() -> int:
    return int(time.time())


def new_id(prefix: str) -> str:
    """Return a short unique identifier with the given prefix."""
    return f"{prefix}_{secrets.token_hex(8)}"


@dataclass(slots=True)
class SSEvent:
    """Server-sent event representation."""

    event: str
    data: dict[str, Any]

    def encode(self) -> bytes:
        payload = orjson.dumps(self.data)
        return f"event: {self.event}\ndata: {payload.decode('utf-8')}\n\n".encode("utf-8")


def response_created_event(response: dict[str, Any], sequence_number: int) -> SSEvent:
    return SSEvent(
        "response.created",
        {
            "type": "response.created",
            "response": response,
            "sequence_number": sequence_number,
        },
    )


def response_in_progress_event(response: dict[str, Any], sequence_number: int) -> SSEvent:
    return SSEvent(
        "response.in_progress",
        {
            "type": "response.in_progress",
            "response": response,
            "sequence_number": sequence_number,
        },
    )


def response_output_delta_event(
    delta: str,
    item_id: str,
    *,
    output_index: int = 0,
    content_index: int = 0,
    sequence_number: int,
) -> SSEvent:
    return SSEvent(
        "response.output_text.delta",
        {
            "type": "response.output_text.delta",
            "delta": delta,
            "output_index": output_index,
            "item_id": item_id,
            "content_index": content_index,
            "sequence_number": sequence_number,
            "logprobs": [],
        },
    )


def response_output_done_event(
    item_id: str,
    *,
    text: str,
    output_index: int = 0,
    content_index: int = 0,
    sequence_number: int,
) -> SSEvent:
    return SSEvent(
        "response.output_text.done",
        {
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": output_index,
            "content_index": content_index,
            "text": text,
            "sequence_number": sequence_number,
            "logprobs": [],
        },
    )


def response_completed_event(response: dict[str, Any], sequence_number: int) -> SSEvent:
    return SSEvent(
        "response.completed",
        {
            "type": "response.completed",
            "response": response,
            "sequence_number": sequence_number,
        },
    )


def response_error_event(response_id: str, message: str, sequence_number: int | None = None) -> SSEvent:
    return SSEvent(
        "response.error",
        {
            "type": "response.error",
            "id": response_id,
            "error": message,
            **({"sequence_number": sequence_number} if sequence_number is not None else {}),
        },
    )


def message_content_block(text: str) -> dict[str, Any]:
    return {"type": "output_text", "text": text}


@dataclass
class ResponseBuilder:
    """Accumulates generation artifacts and builds response payloads."""

    model: str
    conversation_id: str
    previous_response_id: str | None
    response_format: dict[str, Any] | None
    instructions: str | None = None
    metadata: dict[str, Any] | None = None
    response_id: str = field(default_factory=lambda: new_id("resp"))
    message_id: str = field(default_factory=lambda: new_id("msg"))
    created: int = field(default_factory=_now)

    def __post_init__(self) -> None:
        self._text_parts: list[str] = []
        self._raw_parts: list[str] = []
        self._tool_calls: list[ToolCall] = []
        self._final_text: str | None = None
        self.usage = ResponseUsage()

    def append_text(self, delta: str) -> None:
        if not delta:
            return
        self._text_parts.append(delta)
        self.usage.completion_tokens += 1  # heuristic; placeholder without tokenizer stats
        self.usage.total_tokens += 1

    def append_raw(self, delta: str) -> None:
        if not delta:
            return
        self._raw_parts.append(delta)

    def set_prompt_tokens(self, prompt_tokens: int) -> None:
        self.usage.prompt_tokens = prompt_tokens
        self.usage.total_tokens = prompt_tokens + self.usage.completion_tokens

    def finalize_text(self, clean_text: str, tool_calls: list[ToolCall]) -> None:
        self._final_text = clean_text
        self._tool_calls = tool_calls

    @property
    def full_text(self) -> str:
        if self._final_text is not None:
            return self._final_text
        return "".join(self._text_parts)

    @property
    def raw_text(self) -> str:
        return "".join(self._raw_parts) if self._raw_parts else "".join(self._text_parts)

    def build_payload(self) -> ResponsePayload:
        message_text = self.full_text
        output_items: list[ResponseOutputMessage | ResponseFunctionCall] = []

        if message_text:
            output_items.append(
                ResponseOutputMessage(
                    id=self.message_id,
                    content=[message_content_block(message_text)],
                )
            )

        for call in self._tool_calls:
            output_items.append(
                ResponseFunctionCall(
                    id=new_id("call"),
                    name=call.name,
                    arguments=call.arguments,
                    call_id=call.call_id,
                )
            )

        return ResponsePayload(
            id=self.response_id,
            model=self.model,
            created=self.created,
            output=output_items,
            usage=self.usage,
            conversation_id=self.conversation_id,
            previous_response_id=self.previous_response_id,
            response_format=self.response_format,
            instructions=self.instructions,
            metadata=self.metadata,
        )

    def build_response_dict(self, status: str, text: str, tool_calls: list[ToolCall]) -> dict[str, Any]:
        """Construct a dictionary compatible with OpenAI's Responses schema."""

        message_status = "completed" if status == "completed" else "in_progress"
        output_entries: list[dict[str, Any]] = []

        if text:
            output_entries.append(
                {
                    "id": self.message_id,
                    "type": "message",
                    "role": "assistant",
                    "status": message_status,
                    "content": [
                        {
                            "type": "output_text",
                            "text": text,
                            "annotations": [],
                        }
                    ],
                }
            )

        for call in tool_calls:
            output_entries.append(
                {
                    "id": call.call_id,
                    "type": "function_call",
                    "name": call.name,
                    "call_id": call.call_id,
                    "arguments": json.dumps(call.arguments),
                    "status": message_status if status != "completed" else "completed",
                }
            )

        response_dict: dict[str, Any] = {
            "id": self.response_id,
            "object": "response",
            "created_at": float(self.created),
            "model": self.model,
            "status": status,
            "output": output_entries,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": {
                "input_tokens": self.usage.prompt_tokens,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": self.usage.completion_tokens,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": self.usage.total_tokens,
            },
            "conversation": {"id": self.conversation_id},
        }

        if self.previous_response_id:
            response_dict["previous_response_id"] = self.previous_response_id
        if self.instructions:
            response_dict["instructions"] = self.instructions
        if self.metadata:
            response_dict["metadata"] = self.metadata

        return response_dict


__all__ = [
    "ResponseBuilder",
    "SSEvent",
    "new_id",
    "response_created_event",
    "response_in_progress_event",
    "response_output_delta_event",
    "response_output_done_event",
    "response_completed_event",
    "response_error_event",
]
