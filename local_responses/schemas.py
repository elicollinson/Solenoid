"""Pydantic models for OpenAI Responses-compatible requests and responses."""

from __future__ import annotations

import json
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
    strict: bool | None = None

    model_config = ConfigDict(extra="allow")


class ToolDefinition(BaseModel):
    """OpenAI tool wrapper that tolerates legacy function-only payloads."""

    type: ToolType = "function"
    function: ToolFunction | None = None
    name: str | None = None
    description: str | None = None
    parameters: dict[str, Any] | None = None
    strict: bool | None = None

    model_config = ConfigDict(extra="allow")

    @staticmethod
    def _default_parameters(value: dict[str, Any] | None) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def as_openai_tool(self) -> dict[str, Any]:
        """Return a canonical OpenAI Responses tool definition."""
        if self.function is not None:
            payload = self.function.model_dump(mode="json")
        else:
            if not self.name:
                raise ValueError("Function tool definition must include a name")
            payload = {
                "name": self.name,
                "description": self.description,
                "parameters": self._default_parameters(self.parameters),
            }
            if self.strict is not None:
                payload["strict"] = self.strict

        if "parameters" not in payload or payload["parameters"] is None:
            payload["parameters"] = {}

        strict = payload.pop("strict", None)
        tool_def: dict[str, Any] = {
            "type": "function",
            "function": payload,
        }

        effective_strict = self.strict if self.strict is not None else strict
        if effective_strict is not None:
            tool_def["strict"] = effective_strict

        return tool_def

    def model_post_init(self, __context: Any) -> None:  # pragma: no cover - pydantic hook
        if self.function is None and self.name:
            self.function = ToolFunction(
                name=self.name,
                description=self.description,
                parameters=self._default_parameters(self.parameters),
                strict=self.strict,
            )


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
    input: str | list[Any] | None = None
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
            return [self._normalize_message_dict(message.model_dump(mode="json")) for message in self.messages]

        if isinstance(self.input, str):
            return [{"role": "user", "content": self.input}]

        if isinstance(self.input, list):
            normalized: list[dict[str, Any]] = []
            for item in self.input:
                message = self._coerce_input_item(item)
                if message is not None:
                    normalized.append(message)

            if not normalized:
                raise ValueError("No valid messages provided in 'input'")

            return normalized

        raise ValueError("Either 'messages' or 'input' must be provided")

    @classmethod
    def _coerce_input_item(cls, item: Any) -> dict[str, Any] | None:
        """Convert various Responses input item shapes into chat messages."""
        if isinstance(item, MessageInput):
            return cls._normalize_message_dict(item.model_dump(mode="json"))

        if hasattr(item, "model_dump"):
            try:
                item = item.model_dump(mode="json")
            except TypeError:  # pragma: no cover - defensive fallback
                item = item.model_dump()

        if isinstance(item, dict):
            if "role" in item:
                return cls._normalize_message_dict(item)

            item_type = item.get("type")
            if item_type in {"function_call_output", "local_shell_call_output", "computer_call_output"}:
                content = cls._normalize_content(item.get("output", ""))
                message: dict[str, Any] = {"role": "tool", "content": content}
                call_id = item.get("call_id") or item.get("id")
                if call_id:
                    message["tool_call_id"] = call_id
                return message

            if item_type:
                payload = {key: value for key, value in item.items() if key not in {"type"}}
                content = f"[{item_type}]"
                if payload:
                    content = f"{content} {cls._stringify_content(payload)}"
                return {"role": "assistant", "content": content}

            if "content" in item:
                role = item.get("role", "user")
                return {"role": role, "content": cls._normalize_content(item.get("content"))}

            return None

        if isinstance(item, str):
            return {"role": "user", "content": item}

        return None

    @classmethod
    def _normalize_message_dict(cls, message: dict[str, Any]) -> dict[str, Any]:
        role = message.get("role")
        if not isinstance(role, str) or not role:
            raise ValueError("Message is missing a role")

        normalized: dict[str, Any] = {
            "role": role,
            "content": cls._normalize_content(message.get("content")),
        }

        if "tool_call_id" in message and message["tool_call_id"]:
            normalized["tool_call_id"] = message["tool_call_id"]

        return normalized

    @classmethod
    def _normalize_content(cls, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    else:
                        parts.append(cls._stringify_content(part))
                else:
                    parts.append(cls._stringify_content(part))
            return "\n".join(part for part in parts if part)
        return cls._stringify_content(content)

    @staticmethod
    def _stringify_content(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except TypeError:
            return str(value)


class ResponseUsage(BaseModel):
    """Token accounting stub."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    response_cost: float | None = None


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
    tool_calls: list[dict[str, Any]] | None = None
    debug: dict[str, Any] | None = None
    upstream_response_id: str | None = None
    upstream_model: str | None = None
    upstream_provider: str | None = None
    bridged_endpoint: bool = False


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
