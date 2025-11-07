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
    conversation_id: str | None = None
    current_user_messages: Sequence[dict[str, Any]] | None = None


@dataclass(slots=True)
class StreamChunk:
    """Single chunk of streamed text."""

    delta: str
    raw: Any | None = None
    finish_reason: str | None = None
    reasoning_delta: str | None = None
    tool_calls: Sequence[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    response_id: str | None = None
    provider: str | None = None
    model: str | None = None


@dataclass(slots=True)
class GenerationResult:
    """Full generation payload for non-streaming calls."""

    text: str
    finish_reason: str | None = None
    raw: Any | None = None
    reasoning: str | None = None
    tool_calls: Sequence[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    response_id: str | None = None
    provider: str | None = None
    model: str | None = None
    bridged_endpoint: bool = False


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

    if normalized in {"litellm", "lite_llm", "lite"}:
        from .litellm_backend import LiteLLMBackend

        model_config = kwargs.get("model_config")
        if model_config is None:
            raise ValueError("LiteLLM backend requires a model_config instance")
        return LiteLLMBackend(model_config=model_config)

    if normalized in {"google_adk", "adk"}:
        from .google_adk_backend import GoogleAdkBackend

        model_config = kwargs.get("model_config")
        if model_config is None:
            raise ValueError("Google ADK backend requires a model_config instance")
        return GoogleAdkBackend(model_config=model_config)

    raise ValueError(f"Unknown backend: {name}")


__all__ = [
    "Backend",
    "GenerationParams",
    "GenerationResult",
    "StreamChunk",
    "create_backend",
]
