"""Pydantic models for OpenAI Responses-compatible requests and responses."""

from __future__ import annotations

import time
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


Role = Literal["system", "user", "assistant", "tool"]
ToolType = Literal["function"]


class MessageContentText(BaseModel):
    """Minimal text content part."""

    type: Literal["text"] = "text"
    text: str


class MessageInput(BaseModel):
    """Incoming conversation message."""

    role: Role
    content: Any
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class ToolFunction(BaseModel):
    """OpenAI function tool definition."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ToolDefinition(BaseModel):
    """OpenAI tool wrapper around a function definition."""

    type: ToolType = "function"
    function: ToolFunction

    model_config = ConfigDict(extra="allow")


class ResponseFormatJSONSchema(BaseModel):
    """JSON schema based response format."""

    type: Literal["json_schema"]
    json_schema: dict[str, Any]


class ResponseFormatText(BaseModel):
    """Text response format passthrough."""

    type: Literal["text"]


ResponseFormat = ResponseFormatJSONSchema | ResponseFormatText | dict[str, Any]


class ResponsesRequest(BaseModel):
    """Subset of the OpenAI Responses API request schema."""

    model: str
    input: str | list[MessageInput] | None = None
    messages: list[MessageInput] | None = None
    instructions: str | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stream: bool = False
    previous_response_id: str | None = None
    conversation_id: str | None = None
    response_format: ResponseFormat | None = None
    max_output_tokens: int | None = Field(default=None, alias="max_output_tokens")
    temperature: float | None = None
    top_p: float | None = None
    stop: Sequence[str] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @field_validator("max_output_tokens")
    @classmethod
    def _validate_max_tokens(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_output_tokens must be positive")
        return value

    def normalized_messages(self) -> list[dict[str, Any]]:
        """Return normalized messages list for backend consumption."""
        if self.messages:
            return [message.model_dump(mode="json") for message in self.messages]

        if isinstance(self.input, str):
            return [{"role": "user", "content": self.input}]

        if isinstance(self.input, list):
            # Accept raw dicts or MessageInput objects.
            normalized: list[dict[str, Any]] = []
            for item in self.input:
                if isinstance(item, MessageInput):
                    normalized.append(item.model_dump(mode="json"))
                else:
                    normalized.append(MessageInput.model_validate(item).model_dump(mode="json"))
            return normalized

        raise ValueError("Either 'messages' or 'input' must be provided")


class ResponseUsage(BaseModel):
    """Token accounting stub."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ResponseOutputMessage(BaseModel):
    """Assistant message output item."""

    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[dict[str, Any]]


class ResponseFunctionCall(BaseModel):
    """Function call output item."""

    id: str
    type: Literal["function_call"] = "function_call"
    name: str
    arguments: dict[str, Any]
    call_id: str


class ResponsePayload(BaseModel):
    """Final JSON payload returned by the API."""

    id: str
    object: Literal["response"] = "response"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    status: Literal["completed", "in_progress", "queued", "failed"] = "completed"
    output: list[ResponseOutputMessage | ResponseFunctionCall]
    usage: ResponseUsage = Field(default_factory=ResponseUsage)
    conversation_id: str
    previous_response_id: str | None = None
    response_format: ResponseFormat | None = None
    instructions: str | None = None
    metadata: dict[str, Any] | None = None


__all__ = [
    "MessageInput",
    "ResponsesRequest",
    "ResponsePayload",
    "ResponseUsage",
    "ResponseOutputMessage",
    "ResponseFunctionCall",
    "ToolDefinition",
    "ResponseFormat",
]

