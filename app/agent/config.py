# app/agent/config.py
"""Centralized configuration loader for agent prompts and settings."""

import os
import yaml
import logging
from functools import lru_cache
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Project root is ../../ from this file (app/agent/config.py -> project root)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))


@lru_cache(maxsize=1)
def load_settings(config_path: str = "app_settings.yaml") -> dict:
    """Load the application settings from YAML. Results are cached."""
    absolute_config_path = os.path.join(_PROJECT_ROOT, config_path)

    if not os.path.exists(absolute_config_path):
        LOGGER.warning(f"Config file not found at {absolute_config_path}. Using defaults.")
        return {}

    try:
        with open(absolute_config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        LOGGER.error(f"Error loading config from {absolute_config_path}: {e}")
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


def clear_settings_cache():
    """Clear the cached settings. Useful for testing or dynamic reloading."""
    load_settings.cache_clear()
