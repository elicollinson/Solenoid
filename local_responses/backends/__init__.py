"""Backend interface definitions and factory helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, Sequence


@dataclass(slots=True)
class GenerationParams:
    """Common generation options passed to backends."""

    temperature: float = 0.7
    top_p: float = 0.9
    max_output_tokens: int = 1024
    stop: Sequence[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    response_format: dict[str, Any] | None = None


@dataclass(slots=True)
class StreamChunk:
    """Single chunk of streamed text."""

    delta: str
    raw: Any | None = None


@dataclass(slots=True)
class GenerationResult:
    """Full generation payload for non-streaming calls."""

    text: str
    finish_reason: str | None = None
    raw: Any | None = None


class Backend(Protocol):
    """Protocol implemented by model backends."""

    name: str

    async def ensure_ready(self) -> None: ...

    def supports_json_schema(self) -> bool: ...

    async def generate_stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamChunk]: ...

    async def generate_once(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> GenerationResult: ...


def create_backend(name: str, **kwargs: Any) -> Backend:
    """Instantiate a backend by name."""
    normalized = name.lower()
    if normalized in {"mlx", "mlx_granite", "granite"}:
        from .mlx_backend import MLXBackend

        return MLXBackend(**kwargs)

    if normalized in {"llama", "llama_cpp", "llamacpp"}:
        from .llamacpp_backend import LlamaCppBackend

        return LlamaCppBackend(**kwargs)

    raise ValueError(f"Unknown backend: {name}")


__all__ = [
    "Backend",
    "GenerationParams",
    "GenerationResult",
    "StreamChunk",
    "create_backend",
]
