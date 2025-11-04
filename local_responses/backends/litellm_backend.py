"""LiteLLM-backed remote inference backend."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Iterable, Sequence

import litellm
from litellm import Router  # type: ignore[attr-defined]
from litellm.exceptions import (  # type: ignore[attr-defined]
    BadRequestError,
    OpenAIError,
    UnsupportedParamsError,
)

from . import Backend, GenerationParams, GenerationResult, StreamChunk


LOGGER = logging.getLogger("local_responses.backends.litellm")


class LiteLLMBackend(Backend):
    """Backend implementation forwarding requests through LiteLLM."""

    name = "litellm"

    def __init__(
        self,
        *,
        model: str | None = None,
        litellm_model: str | None = None,
        api_key_env: str | None = "OPENAI_API_KEY",
        api_base: str | None = None,
        mode: str = "auto",
        drop_params: bool = True,
        allowed_openai_params: Iterable[str] | None = None,
        additional_drop_params: Iterable[str] | None = None,
        router: bool = False,
        router_config: dict[str, Any] | None = None,
        healthcheck: bool = False,
    ) -> None:
        self.model_id = model or litellm_model or "litellm"
        self.litellm_model = litellm_model or model or "gpt-4o-mini"
        self.api_base = api_base
        self.api_key_env = api_key_env or "OPENAI_API_KEY"
        self.mode = mode
        self.drop_params = drop_params
        self.allowed_openai_params = tuple(allowed_openai_params or ())
        self.additional_drop_params = tuple(additional_drop_params or ())
        self.router_enabled = router
        self.router_config = dict(router_config or {})
        self.healthcheck_enabled = healthcheck

        self._ready = False
        self._router: Router | None = None
        self._last_bridge: bool = False

    def supports_json_schema(self) -> bool:
        """LiteLLM forwards JSON schema constraints where supported."""
        return True

    @property
    def bridged_last_call(self) -> bool:
        """Return whether the last call required endpoint bridging."""
        return self._last_bridge

    async def ensure_ready(self) -> None:
        """Validate configuration and optionally warm up the provider."""
        if self._ready:
            return

        api_key = self._resolve_api_key()
        if not api_key:
            raise RuntimeError(f"Environment variable {self.api_key_env} must be set for LiteLLM backend")

        if self.router_enabled and self._router is None:
            self._router = Router(
                model_list=[
                    {"model_name": self.litellm_model, "litellm_params": self._base_litellm_params(api_key)},
                ],
                **self.router_config,
            )

        # Optional zero-token health check.
        if self.healthcheck_enabled:
            try:
                await self._perform_healthcheck(api_key)
            except Exception:  # pragma: no cover - best effort, surfaced via log
                LOGGER.exception("LiteLLM healthcheck failed")
                raise

        self._ready = True

    async def _perform_healthcheck(self, api_key: str) -> None:
        """Minimal call to verify credentials and routing."""
        payload = {
            "input": [{"role": "user", "content": [{"type": "text", "text": "ping"}]}],
            "model": self.litellm_model,
            "max_output_tokens": 1,
            "stream": False,
        }
        await self._call_responses(payload, api_key=api_key, stream=False)

    async def generate_stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamChunk]:
        await self.ensure_ready()
        api_key = self._resolve_api_key()
        request_payload = self._build_payload(messages, tools, params, stream=True)

        async for chunk in self._stream_with_preferred_endpoint(request_payload, api_key=api_key):
            delta = self._extract_text_delta(chunk)
            finish_reason = self._extract_finish_reason(chunk)
            yield StreamChunk(delta=delta, raw=chunk, finish_reason=finish_reason)

    async def generate_once(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> GenerationResult:
        text_parts: list[str] = []
        finish_reason: str | None = None
        raw: Any | None = None

        async for chunk in self.generate_stream(messages, tools, params):
            if chunk.delta:
                text_parts.append(chunk.delta)
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            raw = chunk.raw

        return GenerationResult(text="".join(text_parts), finish_reason=finish_reason, raw=raw)

    def _resolve_api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    def _base_litellm_params(self, api_key: str) -> dict[str, Any]:
        params: dict[str, Any] = {"model": self.litellm_model, "api_key": api_key}
        if self.api_base:
            params["api_base"] = self.api_base
        return params

    def _build_payload(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.litellm_model,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "stream": stream,
            "stream_options": {"include_usage": True},
        }

        if params.max_output_tokens is not None:
            payload["max_output_tokens"] = params.max_output_tokens
            payload["max_tokens"] = params.max_output_tokens

        if params.stop:
            payload["stop"] = list(params.stop)

        if params.response_format:
            payload["response_format"] = params.response_format

        if tools:
            payload["tools"] = list(tools)

        payload["messages"] = [self._convert_message_for_chat(msg) for msg in messages]
        payload["input"] = [self._convert_message_for_response(msg) for msg in messages]

        return payload

    def _convert_message_for_chat(self, message: dict[str, Any]) -> dict[str, Any]:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, str):
            return {"role": role, "content": content, **({"tool_call_id": message["tool_call_id"]} if "tool_call_id" in message else {})}
        return {"role": role, "content": content, **({"tool_call_id": message["tool_call_id"]} if "tool_call_id" in message else {})}

    def _convert_message_for_response(self, message: dict[str, Any]) -> dict[str, Any]:
        role = message.get("role", "user")
        base: dict[str, Any] = {"role": role}
        if "tool_call_id" in message:
            base["tool_call_id"] = message["tool_call_id"]

        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for entry in content:
                if isinstance(entry, dict) and "type" in entry:
                    parts.append(entry)
                elif isinstance(entry, str):
                    parts.append({"type": "text", "text": entry})
                else:
                    parts.append({"type": "text", "text": str(entry)})
        elif isinstance(content, str):
            parts = [{"type": "text", "text": content}]
        else:
            parts = [{"type": "text", "text": str(content)}]

        base["content"] = parts
        return base

    async def _stream_with_preferred_endpoint(
        self,
        payload: dict[str, Any],
        *,
        api_key: str,
    ) -> AsyncIterator[Any]:
        """Call LiteLLM using responses endpoint first, then fall back."""
        preferred = self.mode
        self._last_bridge = False

        if preferred in {"responses", "auto"}:
            try:
                stream = await self._call_responses(payload, api_key=api_key, stream=True)
                async for chunk in stream:
                    yield chunk
                return
            except (UnsupportedParamsError, BadRequestError, OpenAIError) as exc:
                if preferred == "responses":
                    raise
                LOGGER.debug("responses endpoint unavailable, falling back to chat completions", exc_info=exc)

        self._last_bridge = preferred != "chat_completions"
        stream = await self._call_chat_completions(payload, api_key=api_key, stream=True)
        async for chunk in stream:
            yield chunk

    async def _call_responses(self, payload: dict[str, Any], *, api_key: str, stream: bool) -> Any:
        params = self._payload_for_responses(payload, api_key=api_key, stream=stream)
        if self._router is not None:
            return await self._router.aresponses(**params)
        return await litellm.aresponses(**params)

    async def _call_chat_completions(self, payload: dict[str, Any], *, api_key: str, stream: bool) -> Any:
        params = self._payload_for_chat(payload, api_key=api_key, stream=stream)
        if self._router is not None:
            return await self._router.acompletion(**params)
        return await litellm.acompletion(**params)

    def _payload_for_responses(self, payload: dict[str, Any], *, api_key: str, stream: bool) -> dict[str, Any]:
        args = {
            "input": payload.get("input"),
            "model": payload["model"],
            "temperature": payload.get("temperature"),
            "top_p": payload.get("top_p"),
            "tools": payload.get("tools"),
            "max_output_tokens": payload.get("max_output_tokens"),
            "previous_response_id": payload.get("previous_response_id"),
            "response_format": payload.get("response_format"),
            "stream": stream,
            "stream_options": payload.get("stream_options"),
            "metadata": payload.get("metadata"),
            "api_key": api_key,
        }

        if self.api_base:
            args["api_base"] = self.api_base

        return args

    def _payload_for_chat(self, payload: dict[str, Any], *, api_key: str, stream: bool) -> dict[str, Any]:
        args = {
            "messages": payload.get("messages"),
            "model": payload["model"],
            "temperature": payload.get("temperature"),
            "top_p": payload.get("top_p"),
            "tools": payload.get("tools"),
            "max_tokens": payload.get("max_output_tokens"),
            "stop": payload.get("stop"),
            "stream": stream,
            "stream_options": payload.get("stream_options"),
            "api_key": api_key,
        }
        if self.api_base:
            args["api_base"] = self.api_base
        if payload.get("response_format"):
            args["response_format"] = payload["response_format"]

        return args

    @staticmethod
    def _extract_text_delta(chunk: Any) -> str:
        choices = LiteLLMBackend._extract_choices(chunk)
        if not choices:
            return ""

        delta = LiteLLMBackend._extract_delta_object(choices[0])
        if not delta:
            return ""

        if isinstance(delta, str):
            return delta

        content = None
        if isinstance(delta, dict):
            content = delta.get("content") or delta.get("text")
        else:
            content = getattr(delta, "content", None) or getattr(delta, "text", None)

        if not content:
            return ""

        return LiteLLMBackend._stringify_content(content)

    @staticmethod
    def _extract_finish_reason(chunk: Any) -> str | None:
        choices = LiteLLMBackend._extract_choices(chunk)
        if not choices:
            return None
        choice = choices[0]
        finish_reason = None
        if isinstance(choice, dict):
            finish_reason = choice.get("finish_reason")
        else:
            finish_reason = getattr(choice, "finish_reason", None)
        return finish_reason

    @staticmethod
    def _extract_choices(chunk: Any) -> list[Any]:
        if chunk is None:
            return []
        if isinstance(chunk, dict):
            choices = chunk.get("choices")
            return list(choices or [])
        choices = getattr(chunk, "choices", None)
        if choices is None:
            return []
        if isinstance(choices, list):
            return choices
        return list(choices)

    @staticmethod
    def _extract_delta_object(choice: Any) -> Any:
        if isinstance(choice, dict):
            if "delta" in choice and choice["delta"]:
                return choice["delta"]
            if "message" in choice and choice["message"]:
                return choice["message"]
            return None
        delta = getattr(choice, "delta", None)
        if delta:
            return delta
        return getattr(choice, "message", None)

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                else:
                    parts.append(str(item))
            return "".join(parts)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
            if isinstance(text, list):
                return "".join(str(part) for part in text)
        return str(content)


__all__ = ["LiteLLMBackend"]
