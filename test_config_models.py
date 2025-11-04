from __future__ import annotations

from local_responses.config import (
    ModelConfig,
    ReasoningConfig,
    ReActConfig,
    ServiceConfig,
    TelemetryConfig,
    ThinkingConfig,
)


def test_model_config_defaults_mirror_public_model_id() -> None:
    cfg = ModelConfig(backend="litellm", model_id="public-model", litellm_model=None)
    assert cfg.litellm_model == "public-model"
    assert cfg.mode == "auto"
    assert cfg.allowed_openai_params == []


def test_reasoning_and_thinking_defaults() -> None:
    reasoning = ReasoningConfig()
    thinking = ThinkingConfig()

    assert reasoning.effort == "low"
    assert reasoning.summary == "concise"
    assert reasoning.verbosity is None

    assert thinking.enabled is False
    assert thinking.budget_tokens == 1024


def test_react_defaults_privacy_safe() -> None:
    react = ReActConfig()
    assert react.enabled is False
    assert react.emit_reasoning_to_client is False


def test_service_config_provides_isolated_lists() -> None:
    cfg1 = ModelConfig()
    cfg2 = ModelConfig()
    assert cfg1 is not cfg2
    assert cfg1.allowed_openai_params == []
    cfg1.allowed_openai_params.append("custom")
    assert cfg2.allowed_openai_params == []


def test_service_config_embeds_model_config() -> None:
    service = ServiceConfig()
    assert isinstance(service.model, ModelConfig)


def test_service_config_reasoning_flags_defaults() -> None:
    service = ServiceConfig()
    assert service.allow_reasoning_stream_to_client is False
    assert service.include_reasoning_in_store is True


def test_telemetry_config_defaults() -> None:
    telemetry = TelemetryConfig()
    assert telemetry.enabled is False
    assert telemetry.project_name == "local-responses"
    assert telemetry.api_key_env == "PHOENIX_API_KEY"
