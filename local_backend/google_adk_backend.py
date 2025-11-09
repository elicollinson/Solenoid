"""Google ADK backend that wraps a conversational Agent + Runner."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Sequence

from google.adk.agents import Agent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.load_memory_tool import load_memory
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from ..config import ModelConfig
from .tool_parsing import merge_tool_call_deltas
from .backends import Backend, GenerationParams, GenerationResult, StreamChunk
from memory.adk_sqlite_memory import SqliteMemoryService


logger = logging.getLogger("local_responses.backends.google_adk")


class GoogleAdkBackend(Backend):
    """Backend that proxies generation through the Google Agent Development Kit."""

    name = "google_adk"

    def __init__(self, *, model_config: ModelConfig):
        self._cfg = model_config
        self._session_service = InMemorySessionService()
        self._runner: Runner | None = None
        self._agent: Agent | None = None
        self._ready = False
        self._load_lock = asyncio.Lock()
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_locks_lock = asyncio.Lock()
        self._provider_name = "google_adk"
        self._tools_warning_emitted = False
        self._memory_service: SqliteMemoryService | None = None

    def supports_json_schema(self) -> bool:
        """Delegate JSON schema support to the configured LLM via LiteLLM."""
        return False

    async def ensure_ready(self) -> None:
        if self._ready:
            return

        async with self._load_lock:
            if self._ready:
                return

            self._agent = self._build_agent()
            self._memory_service = self._init_memory_service()
            self._runner = Runner(
                agent=self._agent,
                app_name=self._cfg.adk.app_name,
                session_service=self._session_service,
                memory_service=self._memory_service,
            )
            self._ready = True
            logger.info(
                "Google ADK agent initialized",
                extra={"app_name": self._cfg.adk.app_name, "model": self._cfg.model_id},
            )

    async def generate_stream(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamChunk]:
        await self.ensure_ready()
        self._maybe_warn_tools(tools)

        runner = self._runner
        if runner is None:
            raise RuntimeError("Google ADK runner is not ready")

        new_message = self._build_new_message(messages, params)
        session_id = params.conversation_id or "default-conversation"
        await self._ensure_session(session_id)

        async for event in runner.run_async(
            user_id=self._cfg.adk.user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            chunk = self._event_to_chunk(event)
            if chunk is None:
                continue
            yield chunk

    async def generate_once(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> GenerationResult:
        text_parts: list[str] = []
        finish_reason: str | None = None
        raw: Any | None = None
        aggregated_tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None
        response_id: str | None = None
        upstream_model: str | None = None

        async for chunk in self.generate_stream(messages, tools, params):
            if chunk.delta:
                text_parts.append(chunk.delta)
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            raw = chunk.raw
            if chunk.tool_calls:
                aggregated_tool_calls = merge_tool_call_deltas(
                    aggregated_tool_calls, chunk.tool_calls
                )
            if chunk.usage:
                usage = chunk.usage
            if chunk.response_id:
                response_id = chunk.response_id
            if chunk.model:
                upstream_model = chunk.model

        return GenerationResult(
            text="".join(text_parts),
            finish_reason=finish_reason,
            raw=raw,
            tool_calls=aggregated_tool_calls or None,
            usage=usage,
            response_id=response_id,
            provider=self._provider_name,
            model=upstream_model or self._cfg.model_id,
        )

    def _build_agent(self) -> Agent:
        llm_kwargs = {}
        api_key = self._resolve_api_key()
        if api_key:
            llm_kwargs["api_key"] = api_key
        if self._cfg.api_base:
            llm_kwargs["api_base"] = self._cfg.api_base
        if self._cfg.drop_params is False:
            llm_kwargs["drop_params"] = False

        model_name = self._cfg.litellm_model or self._cfg.model_id
        llm = LiteLlm(model=model_name, **llm_kwargs)

        gen_config = self._build_generation_config()
        agent_kwargs: dict[str, Any] = {
            "name": self._cfg.adk.name,
            "description": self._cfg.adk.description,
            "instruction": self._cfg.adk.instruction,
            "model": llm,
        }
        if gen_config is not None:
            agent_kwargs["generate_content_config"] = gen_config

        tools = self._memory_tools()
        if tools:
            agent_kwargs["tools"] = tools

        return Agent(**agent_kwargs)

    def _build_generation_config(self) -> types.GenerateContentConfig | None:
        cfg = self._cfg
        kwargs: dict[str, Any] = {}
        if cfg.temperature is not None:
            kwargs["temperature"] = cfg.temperature
        if cfg.top_p is not None:
            kwargs["top_p"] = cfg.top_p
        if cfg.max_output_tokens is not None:
            kwargs["max_output_tokens"] = cfg.max_output_tokens
        if cfg.presence_penalty is not None:
            kwargs["presence_penalty"] = cfg.presence_penalty
        if cfg.frequency_penalty is not None:
            kwargs["frequency_penalty"] = cfg.frequency_penalty

        if not kwargs:
            return None
        return types.GenerateContentConfig(**kwargs)

    def _resolve_api_key(self) -> str | None:
        env_name = self._cfg.api_key_env
        if not env_name:
            return None
        return os.environ.get(env_name)

    def _init_memory_service(self) -> SqliteMemoryService | None:
        if self._memory_service is not None:
            return self._memory_service

        mem_cfg = getattr(self._cfg, "adk_memory", None)
        if mem_cfg is None or not mem_cfg.enabled:
            return None

        service = SqliteMemoryService(
            mem_cfg.db_path,
            embedding_device=mem_cfg.embedding_device,
            dense_candidates=mem_cfg.dense_candidates,
            sparse_candidates=mem_cfg.sparse_candidates,
            fuse_top_k=mem_cfg.fuse_top_k,
            rerank_top_n=mem_cfg.rerank_top_n,
            reranker_model=mem_cfg.reranker_model,
            max_events=mem_cfg.max_events,
        )
        self._memory_service = service
        logger.info("SQLite memory enabled", extra={"path": str(mem_cfg.db_path)})
        return service

    def _memory_tools(self) -> list[Any]:
        mem_cfg = getattr(self._cfg, "adk_memory", None)
        if mem_cfg is None or not mem_cfg.enabled:
            return []

        tools: list[Any] = []
        if mem_cfg.preload_tool:
            tools.append(PreloadMemoryTool())
        if mem_cfg.load_tool:
            tools.append(load_memory)
        return tools

    def _maybe_warn_tools(self, tools: Sequence[dict[str, Any]] | None) -> None:
        if not tools or self._tools_warning_emitted:
            return
        logger.warning(
            "Google ADK backend ignores request-scoped tools; configure them on the agent instead."
        )
        self._tools_warning_emitted = True

    def _build_new_message(
        self,
        messages: Sequence[dict[str, Any]],
        params: GenerationParams,
    ) -> types.Content:
        user_messages: list[dict[str, Any]] = list(params.current_user_messages or [])
        if not user_messages and messages:
            user_messages = [messages[-1]]

        parts: list[types.Part] = []
        for message in user_messages:
            if message.get("role", "user") != "user":
                continue
            parts.extend(self._coerce_parts(message.get("content")))

        if not parts and user_messages:
            # Fall back to including whatever text we can even if the role was not "user".
            for message in user_messages:
                parts.extend(self._coerce_parts(message.get("content")))

        if not parts:
            raise ValueError("Unable to extract user content for Google ADK backend")

        return types.Content(role="user", parts=parts)

    def _coerce_parts(self, content: Any) -> list[types.Part]:
        if content is None:
            return []
        if isinstance(content, types.Part):
            return [content]
        if isinstance(content, str):
            return [types.Part(text=content)]
        if isinstance(content, list):
            parts: list[types.Part] = []
            for item in content:
                parts.extend(self._coerce_parts(item))
            return parts
        if isinstance(content, dict):
            segment_type = content.get("type")
            if segment_type == "text" and "text" in content:
                return [types.Part(text=str(content["text"]))]
            if "text" in content:
                return [types.Part(text=str(content["text"]))]
            if "content" in content and isinstance(content["content"], str):
                return [types.Part(text=content["content"])]
            return [types.Part(text=json.dumps(content, ensure_ascii=False))]
        return [types.Part(text=str(content))]

    async def _ensure_session(self, session_id: str) -> None:
        lock = await self._get_session_lock(session_id)
        async with lock:
            existing = await self._session_service.get_session(
                app_name=self._cfg.adk.app_name,
                user_id=self._cfg.adk.user_id,
                session_id=session_id,
            )
            if existing is not None:
                return

            await self._session_service.create_session(
                app_name=self._cfg.adk.app_name,
                user_id=self._cfg.adk.user_id,
                session_id=session_id,
            )

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_lock:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[session_id] = lock
            return lock

    def _event_to_chunk(self, event: Event) -> StreamChunk | None:
        if event.author.lower() == "user":
            return None

        content = event.content
        if content is None:
            return None

        text = self._content_to_text(content)
        tool_calls = self._extract_tool_calls(content)

        if not text and not tool_calls:
            return None

        usage = self._usage_from_event(event)
        finish_reason = self._finish_reason(event)

        return StreamChunk(
            delta=text,
            raw=event,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            usage=usage,
            response_id=event.invocation_id or event.id,
            provider=self._provider_name,
            model=event.model_version or self._cfg.model_id,
        )

    def _content_to_text(self, content: types.Content) -> str:
        if not content.parts:
            return ""

        text_parts: list[str] = []
        for part in content.parts:
            if part.text:
                text_parts.append(part.text)
            elif part.code_execution_result and part.code_execution_result.output:
                text_parts.append(part.code_execution_result.output)
            elif part.function_response and part.function_response.response is not None:
                text_parts.append(
                    json.dumps(part.function_response.response, ensure_ascii=False)
                )

        return "".join(text_parts)

    def _extract_tool_calls(
        self, content: types.Content
    ) -> list[dict[str, Any]] | None:
        if not content.parts:
            return None

        tool_calls: list[dict[str, Any]] = []
        for index, part in enumerate(content.parts):
            func = part.function_call
            if func is None:
                continue
            arguments = func.args or {}
            tool_calls.append(
                {
                    "id": func.id or f"call_{index}",
                    "type": "function",
                    "function": {
                        "name": func.name or "",
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            )

        return tool_calls or None

    def _usage_from_event(self, event: Event) -> dict[str, Any] | None:
        metadata = event.usage_metadata
        if metadata is None:
            return None
        return {
            "prompt_tokens": metadata.prompt_token_count,
            "completion_tokens": metadata.candidates_token_count,
            "total_tokens": metadata.total_token_count,
        }

    def _finish_reason(self, event: Event) -> str | None:
        reason = event.finish_reason
        if reason is None:
            return None
        if hasattr(reason, "name"):
            return reason.name.lower()
        return str(reason)
