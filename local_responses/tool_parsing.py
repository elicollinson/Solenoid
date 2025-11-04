"""Utilities for extracting <tool_call> blocks from model output."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Sequence, Tuple


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

        call_id = payload.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"{prefix}_{len(tool_calls)}"

        tool_calls.append(ToolCall(call_id=call_id, name=name, arguments=arguments, raw_json=raw_payload))
        return ""  # remove the block from text

    cleaned = _TOOL_PATTERN.sub(_replace, text)
    return cleaned, tool_calls


def merge_tool_call_deltas(
    existing: Sequence[dict[str, Any]],
    updates: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge incremental OpenAI tool call deltas into a consolidated list."""

    calls = [deepcopy(call) for call in existing]

    def ensure_index(idx: int) -> dict[str, Any]:
        while len(calls) <= idx:
            calls.append({})
        return calls[idx]

    for update in updates:
        if not isinstance(update, dict):
            continue
        idx = update.get("index")
        if isinstance(idx, int):
            target = ensure_index(idx)
        else:
            target = None
            update_id = update.get("id")
            if isinstance(update_id, str):
                for call in calls:
                    if isinstance(call, dict) and call.get("id") == update_id:
                        target = call
                        break
            if target is None:
                target = {}
                calls.append(target)

        for key, value in update.items():
            if key == "function" and isinstance(value, dict):
                fn = target.setdefault("function", {})
                if not isinstance(fn, dict):
                    target["function"] = fn = {}
                for fn_key, fn_value in value.items():
                    if fn_key == "arguments" and isinstance(fn_value, str):
                        previous = fn.get("arguments", "")
                        fn["arguments"] = f"{previous}{fn_value}"
                    else:
                        fn[fn_key] = fn_value
            elif key == "index":
                target["index"] = value
            else:
                target[key] = value

    return calls


def structured_tool_calls_to_markup(calls: Sequence[dict[str, Any]]) -> str:
    """Render structured tool call payloads into <tool_call> markup."""

    blocks: list[str] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments_payload = json.loads(arguments)
            except json.JSONDecodeError:
                arguments_payload = arguments
        else:
            arguments_payload = arguments

        payload: dict[str, Any] = {"name": name, "arguments": arguments_payload}
        call_id = call.get("id")
        if isinstance(call_id, str) and call_id:
            payload["call_id"] = call_id

        blocks.append(f"<tool_call>{json.dumps(payload, ensure_ascii=False)}</tool_call>")

    return "".join(blocks)


__all__ = [
    "ToolCall",
    "ToolCallParseError",
    "extract_tool_calls",
    "merge_tool_call_deltas",
    "structured_tool_calls_to_markup",
]
