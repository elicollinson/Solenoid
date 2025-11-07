"""Configuration helpers for the local responses service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


BackendName = Literal["mlx_granite", "llama_cpp", "litellm", "google_adk"]


class AdkAgentConfig(BaseModel):
    """Runtime configuration for the Google ADK conversational agent."""

    name: str = "TerminalAssistant"
    description: str = "Conversational agent that powers the local terminal UI."
    instruction: str = (
        "You are a helpful local assistant operating entirely on the user's machine. "
        "Keep answers concise and focus on actionable guidance."
    )
    app_name: str = "local-responses"
    user_id: str = "terminal-user"

    model_config = ConfigDict(extra="forbid")


class AdkMemoryConfig(BaseModel):
    """Controls the local SQLite+FTS+vec memory service exposed to ADK."""

    enabled: bool = True
    db_path: Path = Path("memories.db")
    dense_candidates: int = 80
    sparse_candidates: int = 80
    fuse_top_k: int = 30
    rerank_top_n: int = 12
    embedding_device: str | None = None
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    preload_tool: bool = True
    load_tool: bool = True
    memory_agent_enabled: bool = True
    memory_agent_model: str = "gemma2-2b-it"
    max_events: int = 20

    model_config = ConfigDict(extra="forbid")


class ReasoningConfig(BaseModel):
    """Native reasoning controls for providers that expose reasoning APIs."""

    effort: Literal["minimal", "low", "medium", "high"] = "low"
    summary: Literal["off", "concise", "detailed"] = "concise"
    budget_tokens: int | None = None
    verbosity: Literal["low", "medium", "high"] | None = None

    model_config = ConfigDict(extra="forbid")


class ThinkingConfig(BaseModel):
    """Anthropic Claude thinking budget controls."""

    enabled: bool = False
    budget_tokens: int = 1024

    model_config = ConfigDict(extra="forbid")


class ReActConfig(BaseModel):
    """ReAct emulation options for non-reasoning models."""

    enabled: bool = False
    max_steps: int = 4
    observation_max_tokens: int = 1024
    schema_strict: bool = True
    emit_reasoning_to_client: bool = False

    model_config = ConfigDict(extra="forbid")


class ModelConfig(BaseModel):
    """Model selection and backend options."""

    backend: BackendName = "mlx_granite"
    model_id: str = "mlx_granite_4.0_h_tiny_4bit"
    litellm_model: str | None = None
    api_base: str | None = None
    api_key_env: str | None = "OPENAI_API_KEY"
    mode: Literal["responses", "chat_completions", "auto"] = "auto"
    drop_params: bool = True
    allowed_openai_params: list[str] = Field(default_factory=list)
    additional_drop_params: list[str] = Field(default_factory=list)
    router: bool = False
    router_config: dict[str, Any] = Field(default_factory=dict)
    reasoning: ReasoningConfig | None = None
    anthropic_thinking: ThinkingConfig | None = None
    react: ReActConfig | None = None
    max_output_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    context_window_tokens: int = 16384
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    healthcheck: bool = False
    adk: AdkAgentConfig = Field(default_factory=AdkAgentConfig)
    adk_memory: AdkMemoryConfig = Field(default_factory=AdkMemoryConfig)

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    @model_validator(mode="after")
    def _ensure_litellm_defaults(self) -> "ModelConfig":
        if self.litellm_model is None:
            object.__setattr__(self, "litellm_model", self.model_id)
        return self


class DatabaseConfig(BaseModel):
    """SQLite connection settings."""

    path: Path = Path("local_responses.db")
    pragmas: dict[str, str] = Field(
        default_factory=lambda: {
            "journal_mode": "wal",
            "synchronous": "normal",
        }
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ServiceConfig(BaseModel):
    """Top-level application configuration."""

    host: str = "127.0.0.1"
    port: int = 4000
    api_key: Optional[str] = None
    model: ModelConfig = Field(default_factory=ModelConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    enable_llama_backend: bool = False
    allow_reasoning_stream_to_client: bool = False
    include_reasoning_in_store: bool = True
    telemetry: "TelemetryConfig" = Field(default_factory=lambda: TelemetryConfig())

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TelemetryConfig(BaseModel):
    """Phoenix telemetry configuration."""

    enabled: bool = False
    project_name: str = "local-responses"
    endpoint: str | None = None
    protocol: Literal["http/protobuf", "grpc"] | None = None
    batch: bool = True
    auto_instrument: bool = False
    verbose: bool = False
    api_key_env: str | None = "PHOENIX_API_KEY"
    headers: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


__all__ = [
    "AdkAgentConfig",
    "AdkMemoryConfig",
    "BackendName",
    "DatabaseConfig",
    "ModelConfig",
    "ReasoningConfig",
    "ReActConfig",
    "ServiceConfig",
    "ThinkingConfig",
    "TelemetryConfig",
]
