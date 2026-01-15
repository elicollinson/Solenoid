# app/agent/config.py
"""Centralized configuration loader for agent prompts and settings."""

import yaml
import logging
from functools import lru_cache
from typing import Optional

from resources.backend_config import get_settings_path

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_settings() -> dict:
    """
    Load the application settings from YAML. Results are cached.

    Uses the unified settings path resolution from backend_config,
    which checks for local development settings first, then falls
    back to the platform-specific config directory.
    """
    settings_path = get_settings_path()

    if not settings_path.exists():
        LOGGER.warning(f"Config file not found at {settings_path}. Using defaults.")
        return {}

    try:
        with open(settings_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        LOGGER.error(f"Error loading config from {settings_path}: {e}")
        return {}


def get_agent_prompt(agent_name: str, default: str = "") -> str:
    """
    Retrieve the instruction prompt for a specific agent from settings.

    Args:
        agent_name: The name of the agent (e.g., 'user_proxy_agent', 'prime_agent')
        default: Default prompt to return if not found in settings

    Returns:
        The agent's instruction prompt string
    """
    settings = load_settings()
    agent_prompts = settings.get("agent_prompts", {})

    prompt = agent_prompts.get(agent_name, default)
    if not prompt and not default:
        LOGGER.warning(f"No prompt found for agent '{agent_name}' in settings")

    return prompt


def get_embedding_config() -> dict:
    """
    Retrieve the embedding configuration from settings.

    Returns:
        Dictionary with embedding config, including:
        - provider: 'ollama' (default)
        - host: Ollama server URL (default: http://localhost:11434)
        - model: Embedding model name (default: nomic-embed-text)
    """
    settings = load_settings()
    embeddings = settings.get("embeddings", {})

    return {
        "provider": embeddings.get("provider", "ollama"),
        "host": embeddings.get("host", "http://localhost:11434"),
        "model": embeddings.get("model", "nomic-embed-text"),
    }


def clear_settings_cache():
    """Clear the cached settings. Useful for testing or dynamic reloading."""
    load_settings.cache_clear()
