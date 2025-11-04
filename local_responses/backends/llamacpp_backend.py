"""Stub backend for future llama.cpp integration."""

from __future__ import annotations

from typing import Any, AsyncIterator, Sequence

from . import GenerationParams, GenerationResult, StreamChunk


class LlamaCppBackend:
    """Placeholder backend exposing the required interface."""

    name = "llama_cpp"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._init_args = args
        self._init_kwargs = kwargs

    async def ensure_ready(self) -> None:
        raise NotImplementedError("llama.cpp backend is not yet implemented")

    def supports_json_schema(self) -> bool:
        """llama.cpp can support JSON schema once implemented."""
        return True

    async def generate_stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamChunk]:
        raise NotImplementedError("llama.cpp backend is not yet implemented")

    async def generate_once(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> GenerationResult:
        raise NotImplementedError("llama.cpp backend is not yet implemented")


__all__ = ["LlamaCppBackend"]

