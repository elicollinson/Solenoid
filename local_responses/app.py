"""FastAPI application factory for the local responses service."""

from __future__ import annotations

import logging
import re
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Sequence

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer
from opentelemetry.trace.status import Status, StatusCode

from .adapter_responses import (
    ResponseBuilder,
    response_completed_event,
    response_created_event,
    response_error_event,
    response_in_progress_event,
    response_output_delta_event,
    response_output_done_event,
    response_reasoning_delta_event,
    response_reasoning_done_event,
    response_usage_event,
)
from .backends import GenerationParams, create_backend
from .compaction.context_compactor import ContextCompactor
from .config import ServiceConfig
from .schemas import ResponsePayload, ResponsesRequest
from .store import ConversationStore, ContextWindowManager
from .tool_parsing import (
    ToolCallParseError,
    extract_tool_calls,
    merge_tool_call_deltas,
    structured_tool_calls_to_markup,
)


LOGGER = logging.getLogger("local_responses.app")
TOOL_OPEN = "<tool_call>"
TOOL_CLOSE = "</tool_call>"
GRANITE_CONTEXT_LENGTH = 131_072


def _response_format_to_dict(response_format: Any) -> dict[str, Any] | None:
    if response_format is None:
        return None
    if isinstance(response_format, dict):
        return response_format
    if hasattr(response_format, "model_dump"):
        return response_format.model_dump(mode="json")
    return None


def _load_default_prompt() -> str | None:
    prompt_path = Path(__file__).resolve().parent / "prompts" / "system.txt"
    try:
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8").strip()
    except Exception:  # pragma: no cover - best effort
        LOGGER.exception("Failed to load default system prompt")
    return None


def _find_unclosed_tool_call(text: str) -> int | None:
    opens = [m.start() for m in re.finditer(re.escape(TOOL_OPEN), text)]
    closes = [m.start() for m in re.finditer(re.escape(TOOL_CLOSE), text)]
    if len(opens) > len(closes):
        return opens[len(closes)]
    return None


class ServiceState:
    """Holds shared application state."""

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.store = ConversationStore(config.database.path)
        backend_kwargs: dict[str, Any] = {}
        if config.model.backend in {"litellm", "google_adk"}:
            backend_kwargs["model_config"] = config.model
        self.backend = create_backend(config.model.backend, **backend_kwargs)
        self.context_manager = ContextWindowManager(config.model.context_window_tokens)
        self.default_system_prompt = _load_default_prompt()
        compaction_cfg = getattr(config.model, "compaction", None)
        self.compactor: ContextCompactor | None = None
        if compaction_cfg is not None:
            self.compactor = ContextCompactor(
                store=self.store,
                backend=self.backend,
                context_manager=self.context_manager,
                config=compaction_cfg,
            )
        self.logger = LOGGER
        self.tracer: Tracer | None = self._init_tracer()

    async def ensure_backend_ready(self) -> None:
        try:
            await self.backend.ensure_ready()
        except NotImplementedError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend not available")
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.exception("Backend failed to load")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    def _init_tracer(self) -> Tracer | None:
        telemetry = getattr(self.config, "telemetry", None)
        if telemetry is None or not telemetry.enabled:
            return None

        try:
            from phoenix.otel import register
        except Exception:  # pragma: no cover - import guard
            self.logger.exception("Phoenix telemetry is not available")
            return None

        api_key = None
        if telemetry.api_key_env:
            api_key = os.environ.get(telemetry.api_key_env)

        headers = dict(telemetry.headers or {})

        try:
            register(
                project_name=telemetry.project_name,
                endpoint=telemetry.endpoint,
                batch=telemetry.batch,
                auto_instrument=telemetry.auto_instrument,
                protocol=telemetry.protocol,
                headers=headers or None,
                verbose=telemetry.verbose,
                api_key=api_key,
            )
            tracer = trace.get_tracer("local_responses")
            self.logger.info(
                "Phoenix telemetry initialized",
                extra={
                    "project_name": telemetry.project_name,
                    "endpoint": telemetry.endpoint,
                    "auto_instrument": telemetry.auto_instrument,
                },
            )
            return tracer
        except Exception:  # pragma: no cover - runtime guard
            self.logger.exception("Failed to initialize Phoenix telemetry")
            return None

    @contextmanager
    def start_span(self, name: str, **attributes: Any) -> Iterator[Span | None]:
        if self.tracer is None:
            yield None
            return

        with self.tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                if value is None:
                    continue
                span.set_attribute(f"local_responses.{key}", value)
            yield span

    def annotate_span(self, span: Span | None, *, builder: ResponseBuilder, payload: ResponsePayload) -> None:
        if span is None:
            return

        usage = builder.usage
        span.set_attribute("local_responses.response_id", builder.response_id)
        span.set_attribute("local_responses.status", payload.status)
        span.set_attribute("local_responses.usage.prompt_tokens", usage.prompt_tokens)
        span.set_attribute("local_responses.usage.completion_tokens", usage.completion_tokens)
        span.set_attribute("local_responses.usage.total_tokens", usage.total_tokens)
        span.set_attribute("local_responses.usage.reasoning_tokens", usage.reasoning_tokens)
        span.set_attribute("local_responses.model", builder.model)
        span.set_attribute("local_responses.bridged_endpoint", builder.bridged_endpoint)

        if builder.upstream_response_id:
            span.set_attribute("local_responses.upstream_response_id", builder.upstream_response_id)
        if builder.upstream_provider:
            span.set_attribute("local_responses.upstream_provider", builder.upstream_provider)
        if builder.upstream_model:
            span.set_attribute("local_responses.upstream_model", builder.upstream_model)
        if builder.reasoning_text:
            span.set_attribute("local_responses.reasoning.length", len(builder.reasoning_text))

        if payload.tool_calls:
            span.set_attribute("local_responses.tool_calls.count", len(payload.tool_calls))

        if usage.response_cost is not None:
            span.set_attribute("local_responses.usage.response_cost", usage.response_cost)

    def verify_api_key(self, request: Request) -> None:
        if not self.config.api_key:
            return

        auth_header = request.headers.get("authorization")
        bearer = f"Bearer {self.config.api_key}"
        if auth_header == bearer:
            return
        if request.headers.get("local-api-key") == self.config.api_key:
            return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_state(request: Request) -> ServiceState:
    return request.app.state.service_state


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    service_config = config or ServiceConfig()
    logging.basicConfig(level=logging.INFO)
    state = ServiceState(service_config)

    app = FastAPI(title="Local Responses Service", version="0.1.0")
    app.state.service_state = state

    @app.on_event("shutdown")
    async def shutdown() -> None:  # pragma: no cover - simple resource cleanup
        state.store.close()

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/v1/models")
    async def list_models(state: ServiceState = Depends(get_state)) -> dict[str, Any]:
        return {
            "data": [
                {
                    "id": state.config.model.model_id,
                    "object": "model",
                    "owned_by": "local",
                    "context_length": GRANITE_CONTEXT_LENGTH,
                }
            ],
            "object": "list",
        }

    async def prepare_prompt(
        state: ServiceState,
        req: ResponsesRequest,
        conversation_id: str,
        tools: list[dict[str, Any]] | None,
        normalized_messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        backend = state.backend
        await state.ensure_backend_ready()

        tokenizer = getattr(backend, "tokenizer", None)

        history = (
            state.store.get_history_for_response(req.previous_response_id)
            if req.previous_response_id
            else state.store.get_messages(conversation_id)
        )

        if not history and state.default_system_prompt:
            # Seed conversation with default instructions.
            state.store.append_messages(conversation_id, [{"role": "system", "content": state.default_system_prompt}])
            history = state.store.get_messages(conversation_id)

        compactor = state.compactor
        if compactor and tokenizer is not None:
            try:
                mutated = await compactor.maybe_compact(
                    conversation_id,
                    history,
                    tokenizer,
                    tools,
                )
            except Exception:  # pragma: no cover - defensive logging
                state.logger.exception("Context compaction failed")
            else:
                if mutated:
                    history = (
                        state.store.get_history_for_response(req.previous_response_id)
                        if req.previous_response_id
                        else state.store.get_messages(conversation_id)
                    )

        prompt_ready_history = [
            {"role": msg.get("role", "user"), "content": msg.get("content")}
            for msg in history
        ]
        effective_messages = list(prompt_ready_history)
        if req.instructions:
            effective_messages.append({"role": "system", "content": req.instructions})
        effective_messages.extend(normalized_messages)

        # Persist the user messages for this turn.
        last_input_turn = state.store.append_messages(conversation_id, normalized_messages)

        if tokenizer is not None:
            trimmed = state.context_manager.trim(effective_messages, tokenizer, tools)
        else:  # pragma: no cover - fallback without tokenizer
            trimmed = effective_messages

        return trimmed, last_input_turn

    async def build_generation_params(
        req: ResponsesRequest,
        state: ServiceState,
        conversation_id: str,
        normalized_messages: Sequence[dict[str, Any]],
    ) -> GenerationParams:
        model_cfg = state.config.model
        return GenerationParams(
            temperature=req.temperature if req.temperature is not None else model_cfg.temperature,
            top_p=req.top_p if req.top_p is not None else model_cfg.top_p,
            max_output_tokens=req.max_output_tokens if req.max_output_tokens is not None else model_cfg.max_output_tokens,
            stop=req.stop,
            presence_penalty=req.presence_penalty,
            frequency_penalty=req.frequency_penalty,
            response_format=_response_format_to_dict(req.response_format),
            conversation_id=conversation_id,
            current_user_messages=tuple(normalized_messages),
        )

    def record_response(
        state: ServiceState,
        req: ResponsesRequest,
        conversation_id: str,
        parent_response_id: str | None,
        builder: ResponseBuilder,
        assistant_turn: int,
        payload: ResponsePayload,
    ) -> None:
        state.store.record_response(
            response_id=builder.response_id,
            conversation_id=conversation_id,
            parent_response_id=parent_response_id,
            model=state.config.model.model_id,
            instructions=req.instructions,
            input_payload=req.model_dump(mode="json"),
            output_payload=payload.model_dump(mode="json"),
            last_message_turn=assistant_turn,
        )

    @app.post("/v1/responses")
    async def create_response(
        request: Request,
        req: ResponsesRequest,
        state: ServiceState = Depends(get_state),
    ):
        state.verify_api_key(request)

        try:
            normalized_messages = req.normalized_messages()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        parent_response_id = req.previous_response_id
        conversation_id = req.conversation_id
        if parent_response_id:
            parent_conversation = state.store.get_conversation_id_for_response(parent_response_id)
            if parent_conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="previous_response_id not found")
            if conversation_id and conversation_id != parent_conversation:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="conversation_id does not match previous_response_id",
                )
            conversation_id = parent_conversation

        conversation_id = state.store.ensure_conversation(conversation_id)

        tools_payload = [tool.as_openai_tool() for tool in req.tools] if req.tools else None
        prompt_messages, _ = await prepare_prompt(
            state,
            req,
            conversation_id,
            tools_payload,
            normalized_messages,
        )
        gen_params = await build_generation_params(req, state, conversation_id, normalized_messages)

        backend = state.backend
        tokenizer = getattr(backend, "tokenizer", None)
        if tokenizer is not None:
            try:
                tokens = tokenizer.apply_chat_template(
                    prompt_messages,
                    tools=tools_payload,
                    add_generation_prompt=True,
                    tokenize=True,
                )
                prompt_tokens = len(tokens["input_ids"]) if isinstance(tokens, dict) and "input_ids" in tokens else len(tokens)
            except Exception:  # pragma: no cover - tokenizer may not support tokenization
                prompt_tokens = 0
        else:
            prompt_tokens = 0

        builder = ResponseBuilder(
            model=state.config.model.model_id,
            conversation_id=conversation_id,
            previous_response_id=parent_response_id,
            response_format=_response_format_to_dict(req.response_format),
            instructions=req.instructions,
            metadata=req.metadata,
        )
        builder.set_prompt_tokens(prompt_tokens)

        async def stream_events() -> AsyncIterator[bytes]:
            with state.start_span(
                "local_responses.generate",
                model=state.config.model.model_id,
                backend=state.config.model.backend,
                stream=True,
            ) as span:
                raw_text = ""
                visible_sent = ""
                sequence_number = -1
                tool_call_state: list[dict[str, Any]] = []
                upstream_response_id: str | None = None
                upstream_provider: str | None = None
                upstream_model_name: str | None = None
                allow_reasoning_stream = state.config.allow_reasoning_stream_to_client

                def next_sequence() -> int:
                    nonlocal sequence_number
                    sequence_number += 1
                    return sequence_number

                initial_response = builder.build_response_dict(status="in_progress", text="", tool_calls=[])
                initial_events = [
                    response_created_event(initial_response, next_sequence()),
                    response_in_progress_event(initial_response, next_sequence()),
                ]
                for event in initial_events:
                    yield event.encode()

                try:
                    async for chunk in backend.generate_stream(prompt_messages, tools_payload, gen_params):
                        if chunk.response_id:
                            upstream_response_id = chunk.response_id
                        if chunk.provider:
                            upstream_provider = chunk.provider
                        if chunk.model:
                            upstream_model_name = chunk.model

                        if chunk.reasoning_delta:
                            builder.append_reasoning(chunk.reasoning_delta)
                            if allow_reasoning_stream:
                                yield response_reasoning_delta_event(
                                    chunk.reasoning_delta,
                                    sequence_number=next_sequence(),
                                ).encode()

                        if chunk.usage:
                            builder.merge_usage(chunk.usage)
                            yield response_usage_event(chunk.usage, next_sequence()).encode()

                        if chunk.tool_calls:
                            tool_call_state = merge_tool_call_deltas(tool_call_state, chunk.tool_calls)

                        delta = chunk.delta or ""
                        if not delta:
                            continue

                        builder.append_raw(delta)
                        raw_text += delta

                        unclosed_index = _find_unclosed_tool_call(raw_text)
                        visible_candidate = raw_text if unclosed_index is None else raw_text[:unclosed_index]
                        clean_visible, _ = extract_tool_calls(visible_candidate)
                        new_delta = clean_visible[len(visible_sent) :]
                        if new_delta:
                            builder.append_text(new_delta)
                            visible_sent += new_delta
                            yield response_output_delta_event(
                                new_delta,
                                builder.message_id,
                                sequence_number=next_sequence(),
                            ).encode()

                    if tool_call_state:
                        builder.set_structured_tool_calls(tool_call_state)
                        markup = structured_tool_calls_to_markup(tool_call_state)
                        if markup:
                            builder.append_raw(markup)
                            raw_text += markup

                    builder.finalize_reasoning()
                    if allow_reasoning_stream and builder.reasoning_text:
                        yield response_reasoning_done_event(builder.reasoning_text, next_sequence()).encode()

                    builder.set_backend_metadata(
                        upstream_response_id=upstream_response_id,
                        upstream_provider=upstream_provider,
                        upstream_model=upstream_model_name,
                        bridged=getattr(backend, "bridged_last_call", False),
                    )

                    clean_text, tool_calls = extract_tool_calls(raw_text)
                    builder.finalize_text(clean_text, tool_calls)
                    yield response_output_done_event(
                        builder.message_id,
                        text=clean_text,
                        sequence_number=next_sequence(),
                    ).encode()

                    assistant_turn = state.store.append_messages(
                        conversation_id,
                        [{"role": "assistant", "content": builder.raw_text}],
                    )

                    builder.prepare_debug(include_reasoning=state.config.include_reasoning_in_store)
                    payload = builder.build_payload()
                    final_response = builder.build_response_dict("completed", clean_text, tool_calls)
                    record_response(state, req, conversation_id, parent_response_id, builder, assistant_turn, payload)
                    if span is not None:
                        state.annotate_span(span, builder=builder, payload=payload)
                    yield response_completed_event(final_response, next_sequence()).encode()
                except ToolCallParseError as exc:
                    if span is not None:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                    yield response_error_event(builder.response_id, str(exc), next_sequence()).encode()
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
                except Exception as exc:
                    if span is not None:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                    state.logger.exception("Streaming generation failed")
                    yield response_error_event(builder.response_id, str(exc), next_sequence()).encode()
                    raise

        if req.stream:
            return StreamingResponse(stream_events(), media_type="text/event-stream")

        # Non-streaming flow
        with state.start_span(
            "local_responses.generate",
            model=state.config.model.model_id,
            backend=state.config.model.backend,
            stream=False,
        ) as span:
            try:
                result = await backend.generate_once(prompt_messages, tools_payload, gen_params)
            except ToolCallParseError as exc:  # pragma: no cover
                if span is not None:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

            raw_text = result.text or ""
            builder.append_raw(raw_text)

            if result.tool_calls:
                structured_calls = merge_tool_call_deltas([], result.tool_calls)
                builder.set_structured_tool_calls(structured_calls)
                markup = structured_tool_calls_to_markup(structured_calls)
                if markup:
                    builder.append_raw(markup)
                    raw_text += markup

            if result.reasoning:
                builder.append_reasoning(result.reasoning)

            if result.usage:
                builder.merge_usage(result.usage)

            builder.finalize_reasoning()
            builder.set_backend_metadata(
                upstream_response_id=result.response_id,
                upstream_provider=result.provider,
                upstream_model=result.model,
                bridged=result.bridged_endpoint,
            )

            clean_text, tool_calls = extract_tool_calls(raw_text)
            builder.finalize_text(clean_text, tool_calls)
            if clean_text:
                builder.append_text(clean_text)

            assistant_turn = state.store.append_messages(
                conversation_id,
                [{"role": "assistant", "content": builder.raw_text}],
            )

            builder.prepare_debug(include_reasoning=state.config.include_reasoning_in_store)
            payload = builder.build_payload()
            record_response(state, req, conversation_id, parent_response_id, builder, assistant_turn, payload)
            if span is not None:
                state.annotate_span(span, builder=builder, payload=payload)
            return JSONResponse(payload.model_dump(mode="json"))

    return app
