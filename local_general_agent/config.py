"""Configuration management for the local_general_agent package."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Configuration file lives alongside the package for now so that
# settings persist between runs without additional setup.
_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"
DEFAULT_THEME = "dark"
DEFAULT_CONTEXT_WINDOW = 16_384
DEFAULT_SEARCH_PROVIDER = None
VALID_SEARCH_PROVIDERS = {"google_cse", "serpapi_google", "brave"}


@dataclass
class SearchConfig:
    """Persisted configuration for the universal search tool."""

    enabled: bool = False
    provider: str | None = DEFAULT_SEARCH_PROVIDER
    credentials: dict[str, str] = field(default_factory=dict)

    def credential(self, key: str) -> str | None:
        value = self.credentials.get(key)
        return value if isinstance(value, str) and value else None


@dataclass
class AppConfig:
    """Simple application configuration model."""

    theme: str = DEFAULT_THEME
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW
    search: SearchConfig = field(default_factory=SearchConfig)
    extras: dict[str, Any] = field(default_factory=dict)


def load_config(available_themes: set[str]) -> AppConfig:
    """Load configuration from disk, falling back to defaults if required."""
    data = _load_settings_dict()

    theme = data.get("theme", DEFAULT_THEME)
    if theme not in available_themes:
        theme = DEFAULT_THEME

    context_tokens = data.get("context_window_tokens", DEFAULT_CONTEXT_WINDOW)
    if not isinstance(context_tokens, int) or context_tokens <= 0:
        context_tokens = DEFAULT_CONTEXT_WINDOW

    search_blob = data.get("search") or {}
    search_config = _coerce_search_config(search_blob)

    known_keys = {"theme", "context_window_tokens", "search"}
    extras = {key: value for key, value in data.items() if key not in known_keys}

    config = AppConfig(
        theme=theme,
        context_window_tokens=context_tokens,
        search=search_config,
        extras=extras,
    )

    # Keep the on-disk representation in sync with any defaults we enforce.
    save_config(config)
    return config


def save_config(config: AppConfig) -> None:
    """Persist configuration to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "theme": config.theme,
        "context_window_tokens": config.context_window_tokens,
        "search": {
            "enabled": config.search.enabled,
            "provider": config.search.provider,
            "credentials": dict(config.search.credentials),
        },
        **config.extras,
    }
    _CONFIG_FILE.write_text(json.dumps(data, indent=2))


def config_path() -> Path:
    """Expose the path to the configuration file for other modules."""
    return _CONFIG_FILE


def load_settings_dict() -> dict[str, Any]:
    """Return the raw settings dictionary from disk."""
    return dict(_load_settings_dict())


def _load_settings_dict() -> dict[str, Any]:
    if not _CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(_CONFIG_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _coerce_search_config(raw: Any) -> SearchConfig:
    if not isinstance(raw, dict):
        return SearchConfig()

    enabled = bool(raw.get("enabled", False))
    provider = raw.get("provider")
    if provider not in VALID_SEARCH_PROVIDERS:
        provider = DEFAULT_SEARCH_PROVIDER

    credentials_raw = raw.get("credentials") or {}
    credentials: dict[str, str] = {}
    if isinstance(credentials_raw, dict):
        for key, value in credentials_raw.items():
            if isinstance(key, str) and isinstance(value, str) and value:
                credentials[key] = value

    return SearchConfig(enabled=enabled, provider=provider, credentials=credentials)
