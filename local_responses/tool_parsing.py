"""Utilities for extracting <tool_call> blocks from model output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Tuple


class ToolCallParseError(ValueError):
    """Raised when a tool call block cannot be parsed."""


_TOOL_PATTERN = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class ToolCall:
    """Structured representation of a parsed tool call."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    raw_json: str


def extract_tool_calls(text: str, prefix: str = "auto") -> Tuple[str, list[ToolCall]]:
    """Remove <tool_call> blocks from *text* and return structured payloads.

    Args:
        text: Model output potentially containing <tool_call>...</tool_call> spans.
        prefix: Identifier prefix used when generating call IDs.

    Returns:
        A tuple of (clean_text, tool_calls).

    Raises:
        ToolCallParseError: if JSON payloads cannot be parsed or required keys are missing.
    """

    tool_calls: list[ToolCall] = []

    def _replace(match: re.Match[str]) -> str:
        raw_payload = match.group(1).strip()
        if not raw_payload:
            raise ToolCallParseError("Empty tool call payload encountered")

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ToolCallParseError(f"Invalid tool call JSON: {exc}") from exc

        name = payload.get("name")
        if not isinstance(name, str) or not name:
            raise ToolCallParseError("Tool call missing 'name' field")

        arguments = payload.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ToolCallParseError("Tool call arguments string is not valid JSON") from exc

        if not isinstance(arguments, dict):
            raise ToolCallParseError("Tool call arguments must be an object")

        call_id = f"{prefix}_{len(tool_calls)}"
        tool_calls.append(ToolCall(call_id=call_id, name=name, arguments=arguments, raw_json=raw_payload))
        return ""  # remove the block from text

    cleaned = _TOOL_PATTERN.sub(_replace, text)
    return cleaned, tool_calls


__all__ = ["ToolCall", "ToolCallParseError", "extract_tool_calls"]

