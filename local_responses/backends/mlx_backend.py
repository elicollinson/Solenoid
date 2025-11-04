"""MLX-based backend implementation using mlx-lm."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, AsyncIterator, Sequence

from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler

from . import Backend, GenerationParams, GenerationResult, StreamChunk


_DEFAULT_REPOS = [
    "lmstudio-community/granite-4.0-h-tiny-MLX-4bit",
    "mlx-community/granite-4.0-h-tiny-4bit",
]


logger = logging.getLogger("local_responses.backends.mlx")


class MLXBackend:
    """MLX backend wrapping mlx_lm APIs."""

    name = "mlx_granite"

    def __init__(
        self,
        repo_candidates: Sequence[str] | None = None,
        tokenizer_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.repo_candidates: Sequence[str] = tuple(repo_candidates or _DEFAULT_REPOS)
        self.tokenizer_kwargs = tokenizer_kwargs or {}
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_lock = asyncio.Lock()

    def supports_json_schema(self) -> bool:
        """MLX Granite backend does not support JSON schema constrained output."""
        return False

    async def ensure_ready(self) -> None:
        """Ensure the model and tokenizer are loaded."""
        await self._ensure_loaded()

    @property
    def tokenizer(self) -> Any | None:
        return self._tokenizer

    async def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        async with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return

            last_exc: Exception | None = None
            for repo_id in self.repo_candidates:
                try:
                    logger.info("Loading MLX model", extra={"repo_id": repo_id})
                    model, tokenizer = await asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda rid=repo_id: load(rid, tokenizer_config=self.tokenizer_kwargs),
                    )
                    self._model = model
                    self._tokenizer = tokenizer
                    logger.info("Loaded MLX model", extra={"repo_id": repo_id})
                    return
                except Exception as exc:  # pragma: no cover - depends on environment
                    logger.exception("Failed to load MLX repo", extra={"repo_id": repo_id})
                    last_exc = exc

            raise RuntimeError("Unable to load MLX Granite model") from last_exc

    async def generate_stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamChunk]:
        await self._ensure_loaded()
        assert self._model is not None and self._tokenizer is not None  # mypy assurance

        prompt = self._tokenizer.apply_chat_template(
            list(messages),
            tools=list(tools) if tools else None,
            add_generation_prompt=True,
        )

        kwargs: dict[str, Any] = {}
        if params.max_output_tokens is not None:
            kwargs["max_tokens"] = params.max_output_tokens

        sampler_args: dict[str, Any] = {}
        if params.temperature is not None:
            sampler_args["temp"] = params.temperature
        if params.top_p is not None:
            sampler_args["top_p"] = params.top_p
        sampler = make_sampler(**sampler_args) if sampler_args else None
        if sampler is not None:
            kwargs["sampler"] = sampler
        if params.stop:
            kwargs["stop"] = list(params.stop)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[StreamChunk | Exception | None] = asyncio.Queue()

        def run_generation() -> None:
            try:
                for chunk in stream_generate(self._model, self._tokenizer, prompt, **kwargs):
                    delta = getattr(chunk, "text", "") or ""
                    finish_reason = getattr(chunk, "finish_reason", None)
                    queue_put = StreamChunk(delta=delta, raw=chunk, finish_reason=finish_reason)
                    loop.call_soon_threadsafe(queue.put_nowait, queue_put)
            except Exception as exc:  # pragma: no cover - depends on runtime errors
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=run_generation, name="mlx-generate", daemon=True)
        thread.start()

        while True:
            item = await queue.get()
            if item is None:
                break

            if isinstance(item, Exception):
                raise item

            yield item

    async def generate_once(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> GenerationResult:
        text_parts: list[str] = []
        finish_reason: str | None = None
        raw_last: Any | None = None

        async for chunk in self.generate_stream(messages, tools, params):
            if chunk.delta:
                text_parts.append(chunk.delta)
            raw_last = chunk.raw
            finish_reason_candidate = getattr(chunk.raw, "finish_reason", None)
            if finish_reason_candidate:
                finish_reason = finish_reason_candidate

        return GenerationResult(text="".join(text_parts), finish_reason=finish_reason, raw=raw_last)
