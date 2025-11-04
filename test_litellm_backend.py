# ruff: noqa: S101 - simple asserts for tests

from __future__ import annotations

from typing import Any, AsyncIterator, Sequence

import asyncio
import pytest

from local_responses.backends import GenerationParams
from local_responses.backends.litellm_backend import LiteLLMBackend
from local_responses.config import ModelConfig, ReasoningConfig, ThinkingConfig


class _AsyncStream:
    """Helper to produce async iteration from a list of chunks."""

    def __init__(self, chunks: Sequence[Any]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self) -> AsyncIterator[Any]:
        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


def test_generate_stream_uses_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("litellm.get_llm_provider", lambda model: "openai")

    async def fake_aresponses(**kwargs: Any) -> _AsyncStream:
        nonlocal called
        called = kwargs
        chunks = [
            {"choices": [{"delta": {"content": [{"type": "output_text", "text": "Hello"}]}}]},
            {"choices": [{"delta": {"content": [{"type": "output_text", "text": "!"}]}, "finish_reason": "stop"}]},
        ]
        return _AsyncStream(chunks)

    monkeypatch.setattr("litellm.aresponses", fake_aresponses)

    model_cfg = ModelConfig(backend="litellm", model_id="test-model", litellm_model="openai/o3-mini", mode="responses")
    backend = LiteLLMBackend(model_config=model_cfg)
    messages = [{"role": "user", "content": "Hi"}]

    params = GenerationParams(temperature=0.2, top_p=0.8, max_output_tokens=128)
    deltas: list[str] = []

    async def _consume() -> None:
        async for chunk in backend.generate_stream(messages, tools=None, params=params):
            deltas.append(chunk.delta)

    asyncio.run(_consume())

    assert "".join(deltas) == "Hello!"
    assert called["model"] == "openai/o3-mini"
    assert called["stream"] is True
    assert called["stream_options"] == {"include_usage": True}
    assert backend.bridged_last_call is False


def test_generate_stream_falls_back_to_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("litellm.get_llm_provider", lambda model: "openai")

    from litellm.exceptions import UnsupportedParamsError

    async def fake_aresponses(**kwargs: Any) -> _AsyncStream:
        raise UnsupportedParamsError("responses not supported")

    called_completion: dict[str, Any] = {}

    async def fake_acompletion(**kwargs: Any) -> _AsyncStream:
        nonlocal called_completion
        called_completion = kwargs
        chunks = [{"choices": [{"delta": {"content": "Hi"}}]}, {"choices": [{"delta": {"content": "!"}, "finish_reason": "stop"}]}]
        return _AsyncStream(chunks)

    monkeypatch.setattr("litellm.aresponses", fake_aresponses)
    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    model_cfg = ModelConfig(backend="litellm", model_id="fallback", litellm_model="openai/gpt-4o-mini", mode="auto")
    backend = LiteLLMBackend(model_config=model_cfg)
    messages = [{"role": "user", "content": "Hi there"}]
    params = GenerationParams()

    chunks: list[Any] = []

    async def _consume() -> None:
        async for chunk in backend.generate_stream(messages, tools=None, params=params):
            chunks.append(chunk)

    asyncio.run(_consume())

    assert "".join(ch.delta for ch in chunks) == "Hi!"
    assert called_completion["model"] == "openai/gpt-4o-mini"
    assert backend.bridged_last_call is True


def test_additional_drop_params_force_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("litellm.get_llm_provider", lambda model: "openai")

    async def fake_acompletion(**kwargs: Any) -> _AsyncStream:
        fake_acompletion.captured = kwargs  # type: ignore[attr-defined]
        chunks = [
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]},
        ]
        return _AsyncStream(chunks)

    fake_acompletion.captured = {}  # type: ignore[attr-defined]

    monkeypatch.setattr("litellm.acompletion", fake_acompletion)
    monkeypatch.setattr("litellm.get_supported_openai_params", lambda model, custom_llm_provider=None: ["model", "messages", "stream", "stream_options"])

    model_cfg = ModelConfig(
        backend="litellm",
        model_id="chat",
        litellm_model="openai/gpt-4o-mini",
        mode="chat_completions",
        drop_params=True,
        additional_drop_params=["temperature"],
        allowed_openai_params=["custom_field"],
    )
    backend = LiteLLMBackend(model_config=model_cfg)

    params = GenerationParams(temperature=0.9)
    messages = [{"role": "user", "content": "Ping"}]

    async def _consume() -> None:
        async for _ in backend.generate_stream(messages, tools=None, params=params):
            break

    asyncio.run(_consume())

    captured = fake_acompletion.captured  # type: ignore[attr-defined]
    assert "temperature" not in captured
    assert captured.get("drop_params") is True


def test_reasoning_payload_includes_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("litellm.get_llm_provider", lambda model: "openai")

    captured: dict[str, Any] = {}

    async def fake_stream(self, payload: dict[str, Any], *, api_key: str):  # type: ignore[override]
        captured["payload"] = payload
        async for item in _AsyncStream([{"choices": []}]):
            yield item

    monkeypatch.setattr(
        "local_responses.backends.litellm_backend.LiteLLMBackend._stream_with_preferred_endpoint",
        fake_stream,
    )

    model_cfg = ModelConfig(
        backend="litellm",
        model_id="reason",
        litellm_model="openai/o3-mini",
        mode="responses",
        reasoning=ReasoningConfig(effort="medium", summary="detailed", verbosity="high", budget_tokens=333),
        anthropic_thinking=ThinkingConfig(enabled=True, budget_tokens=2048),
    )
    backend = LiteLLMBackend(model_config=model_cfg)
    messages = [{"role": "user", "content": "Hi"}]
    params = GenerationParams(max_output_tokens=222)

    async def _consume() -> None:
        async for _ in backend.generate_stream(messages, tools=None, params=params):
            break

    asyncio.run(_consume())

    payload = captured["payload"]
    assert payload["reasoning"] == {"effort": "medium", "summary": "detailed"}
    assert payload["text"] == {"verbosity": "high"}
    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert payload["max_output_tokens"] == 222
    assert payload["max_tokens"] == 222


def test_reasoning_budget_used_when_no_param(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("litellm.get_llm_provider", lambda model: "openai")

    captured: dict[str, Any] = {}

    async def fake_stream(self, payload: dict[str, Any], *, api_key: str):  # type: ignore[override]
        captured["payload"] = payload
        async for item in _AsyncStream([{"choices": []}]):
            yield item

    monkeypatch.setattr(
        "local_responses.backends.litellm_backend.LiteLLMBackend._stream_with_preferred_endpoint",
        fake_stream,
    )

    model_cfg = ModelConfig(
        backend="litellm",
        model_id="reason",
        litellm_model="openai/o1-preview",
        mode="responses",
        reasoning=ReasoningConfig(effort="high", budget_tokens=555),
    )
    backend = LiteLLMBackend(model_config=model_cfg)
    messages = [{"role": "user", "content": "Hello"}]
    params = GenerationParams(max_output_tokens=None)

    async def _consume() -> None:
        async for _ in backend.generate_stream(messages, tools=None, params=params):
            break

    asyncio.run(_consume())

    payload = captured["payload"]
    assert payload["max_output_tokens"] == 555
    assert payload["max_tokens"] == 555


def test_usage_and_tool_call_aggregation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("litellm.get_llm_provider", lambda model: "openai")

    async def fake_stream(self, payload: dict[str, Any], *, api_key: str):  # type: ignore[override]
        chunks = [
            {
                "choices": [
                    {
                        "delta": {
                            "content": "Hello",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "tool", "arguments": ""},
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": '{"value": 1'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": ", \"more\": 2}"},
                                }
                            ]
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
        ]
        async for item in _AsyncStream(chunks):
            yield item

    monkeypatch.setattr(
        "local_responses.backends.litellm_backend.LiteLLMBackend._stream_with_preferred_endpoint",
        fake_stream,
    )

    model_cfg = ModelConfig(backend="litellm", model_id="tool", litellm_model="openai/gpt-4o-mini", mode="chat_completions")
    backend = LiteLLMBackend(model_config=model_cfg)
    messages = [{"role": "user", "content": "Hi there"}]
    params = GenerationParams()

    result = asyncio.run(backend.generate_once(messages, tools=None, params=params))

    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5}
    assert result.tool_calls is not None
    assert result.tool_calls[0]["function"]["arguments"] == '{"value": 1, "more": 2}'
