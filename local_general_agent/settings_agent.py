"""Settings management sub-agent with dynamic configuration tools."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Annotated, Any, Callable

from agents import Agent, function_tool


def _format_settings(settings: dict[str, Any]) -> str:
    if not settings:
        return "No settings found on disk. The application is using defaults."

    lines = []
    for key in sorted(settings):
        value = settings[key]
        type_name = type(value).__name__
        lines.append(f"- {key} ({type_name}): {value!r}")
    return "\n".join(lines)


def _parse_value(raw_value: str) -> Any:
    text = raw_value.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to treating the value as a plain string if it isn't valid JSON.
        return text


def _coerce_value(parsed: Any, current: Any | None) -> Any:
    if current is None:
        return parsed

    if isinstance(current, bool):
        if isinstance(parsed, bool):
            return parsed
        if isinstance(parsed, str):
            lowered = parsed.lower()
            if lowered in {"true", "1"}:
                return True
            if lowered in {"false", "0"}:
                return False
        raise ValueError("Expected a boolean value (true/false).")

    if isinstance(current, int) and not isinstance(current, bool):
        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            return int(parsed)
        if isinstance(parsed, str) and parsed.isdigit():
            return int(parsed)
        raise ValueError("Expected an integer value.")

    if isinstance(current, float):
        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            return float(parsed)
        if isinstance(parsed, str):
            try:
                return float(parsed)
            except ValueError as exc:
                raise ValueError("Expected a numeric value.") from exc
        raise ValueError("Expected a numeric value.")

    if isinstance(current, str):
        if isinstance(parsed, str):
            return parsed
        return str(parsed)

    return parsed


def create_settings_agent(
    load_settings: Callable[[], dict[str, Any]],
    apply_setting: Callable[[str, Any], str],
    *,
    model: str | None = None,
) -> Agent:
    """Create an agent capable of inspecting and updating application settings."""

    @function_tool(name_override="list_settings")
    def list_settings() -> str:
        """
        Enumerate current settings from disk.

        Returns:
            A newline-delimited list of setting names, types, and current values.
        """
        settings = load_settings()
        return _format_settings(settings)

    @function_tool(name_override="update_setting")
    def update_setting(
        key: Annotated[str, "Name of the setting to update or create."],
        value: Annotated[str, "New value expressed in JSON (e.g. 42, \"dark\", true)."],
    ) -> str:
        """
        Update a setting dynamically.

        Args:
            key: Existing setting name, or a new name to create.
            value: JSON literal representing the new value.

        Returns:
            Confirmation message describing the change.
        """
        settings = load_settings()
        current_value = settings.get(key)
        parsed = _parse_value(value)
        try:
            coerced = _coerce_value(parsed, current_value)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(str(exc)) from exc

        changed_message = apply_setting(key, coerced)
        new_snapshot = load_settings()
        summary_lines = [
            changed_message,
            "",
            "Updated settings snapshot:",
            _format_settings(new_snapshot),
        ]
        return "\n".join(summary_lines)

    instructions = dedent(
        """
        You are a configuration specialist responsible for managing the application's settings file.

        Workflow:
        1. Call `list_settings` to understand available keys and current values.
        2. Use `update_setting` to modify a specific entry. Always pass JSON literals for values.
        3. Confirm the change by restating the final setting value.

        Constraints:
        - Never guess values; verify the target key before updating.
        - Do not modify multiple keys in one tool call—invoke `update_setting` separately per setting.
        - Keep explanations concise and reference the relevant keys explicitly.
        """
    ).strip()

    agent_kwargs = {
        "name": "Settings Manager",
        "instructions": instructions,
        "tools": [list_settings, update_setting],
        "handoff_description": (
            "Use me to inspect current settings and apply updates to the application's configuration file."
        ),
    }
    if model:
        agent_kwargs["model"] = model
    return Agent(**agent_kwargs)


__all__ = ["create_settings_agent"]
