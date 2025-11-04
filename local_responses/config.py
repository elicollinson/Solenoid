"""Configuration helpers for the local responses service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


BackendName = Literal["mlx_granite", "llama_cpp"]


@dataclass
class ModelConfig:
    """Model selection and backend options."""

    backend: BackendName = "mlx_granite"
    model_id: str = "mlx_granite_4.0_h_tiny_4bit"
    max_output_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    context_window_tokens: int = 16384


@dataclass
class DatabaseConfig:
    """SQLite connection settings."""

    path: Path = Path("local_responses.db")
    pragmas: dict[str, str] = field(
        default_factory=lambda: {
            "journal_mode": "wal",
            "synchronous": "normal",
        }
    )


@dataclass
class ServiceConfig:
    """Top-level application configuration."""

    host: str = "127.0.0.1"
    port: int = 4000
    api_key: Optional[str] = None
    model: ModelConfig = field(default_factory=ModelConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    enable_llama_backend: bool = False
