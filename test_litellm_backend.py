# ruff: noqa: S101 - simple asserts for tests

from __future__ import annotations

from typing import Any, AsyncIterator, Sequence

import asyncio
import pytest

from local_responses.backends import GenerationParams
from local_responses.backends.litellm_backend import LiteLLMBackend


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

    async def fake_aresponses(**kwargs: Any) -> _AsyncStream:
        nonlocal called
        called = kwargs
        chunks = [
            {"choices": [{"delta": {"content": [{"type": "output_text", "text": "Hello"}]}}]},
            {"choices": [{"delta": {"content": [{"type": "output_text", "text": "!"}]}, "finish_reason": "stop"}]},
        ]
        return _AsyncStream(chunks)

    monkeypatch.setattr("litellm.aresponses", fake_aresponses)

    backend = LiteLLMBackend(litellm_model="openai/o3-mini", mode="responses")
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

    backend = LiteLLMBackend(litellm_model="openai/gpt-4o-mini", mode="auto")
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
