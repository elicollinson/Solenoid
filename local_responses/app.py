"""FastAPI application factory for the local responses service."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from .adapter_responses import (
    ResponseBuilder,
    response_completed_event,
    response_created_event,
    response_error_event,
    response_in_progress_event,
    response_output_delta_event,
    response_output_done_event,
)
from .backends import GenerationParams, create_backend
from .config import ServiceConfig
from .schemas import ResponsePayload, ResponsesRequest
from .store import ConversationStore, ContextWindowManager
from .tool_parsing import ToolCallParseError, extract_tool_calls


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
        self.backend = create_backend(config.model.backend)
        self.context_manager = ContextWindowManager(config.model.context_window_tokens)
        self.default_system_prompt = _load_default_prompt()
        self.logger = LOGGER

    async def ensure_backend_ready(self) -> None:
        try:
            await self.backend.ensure_ready()
        except NotImplementedError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend not available")
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.exception("Backend failed to load")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

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

        history = state.store.get_history_for_response(req.previous_response_id) if req.previous_response_id else state.store.get_messages(conversation_id)

        if not history and state.default_system_prompt:
            # Seed conversation with default instructions.
            state.store.append_messages(conversation_id, [{"role": "system", "content": state.default_system_prompt}])
            history = state.store.get_messages(conversation_id)

        effective_messages = list(history)
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

    async def build_generation_params(req: ResponsesRequest, state: ServiceState) -> GenerationParams:
        model_cfg = state.config.model
        return GenerationParams(
            temperature=req.temperature if req.temperature is not None else model_cfg.temperature,
            top_p=req.top_p if req.top_p is not None else model_cfg.top_p,
            max_output_tokens=req.max_output_tokens if req.max_output_tokens is not None else model_cfg.max_output_tokens,
            stop=req.stop,
            presence_penalty=req.presence_penalty,
            frequency_penalty=req.frequency_penalty,
            response_format=_response_format_to_dict(req.response_format),
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
        gen_params = await build_generation_params(req, state)

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
            raw_text = ""
            visible_sent = ""
            sequence_number = -1

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

                payload = builder.build_payload()
                final_response = builder.build_response_dict("completed", clean_text, tool_calls)
                record_response(state, req, conversation_id, parent_response_id, builder, assistant_turn, payload)
                yield response_completed_event(final_response, next_sequence()).encode()
            except ToolCallParseError as exc:
                yield response_error_event(builder.response_id, str(exc), next_sequence()).encode()
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
            except Exception as exc:
                state.logger.exception("Streaming generation failed")
                yield response_error_event(builder.response_id, str(exc), next_sequence()).encode()
                raise

        if req.stream:
            return StreamingResponse(stream_events(), media_type="text/event-stream")

        # Non-streaming flow
        try:
            result = await backend.generate_once(prompt_messages, tools_payload, gen_params)
        except ToolCallParseError as exc:  # pragma: no cover
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        raw_text = result.text or ""
        builder.append_raw(raw_text)
        clean_text, tool_calls = extract_tool_calls(raw_text)
        builder.finalize_text(clean_text, tool_calls)
        if clean_text:
            builder.append_text(clean_text)

        assistant_turn = state.store.append_messages(
            conversation_id,
            [{"role": "assistant", "content": builder.raw_text}],
        )

        payload = builder.build_payload()
        record_response(state, req, conversation_id, parent_response_id, builder, assistant_turn, payload)
        return JSONResponse(payload.model_dump(mode="json"))

    return app
