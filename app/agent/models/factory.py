import os
import yaml
import logging
from typing import Optional
from google.adk.models.lite_llm import LiteLlm
from app.agent.ollama.ollama_app import start_ollama_server, ensure_model_available

LOGGER = logging.getLogger(__name__)

DEFAULT_MODEL = "granite4:tiny-h"
DEFAULT_PROVIDER = "ollama_chat"

def load_config(config_path: str = "app_settings.yaml") -> dict:
    """Loads the application settings from YAML."""
    # Try to find the config file relative to the project root
    # This file is in app/agent/models/factory.py
    # Project root is ../../../ from here
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    absolute_config_path = os.path.join(project_root, config_path)
    
    if os.path.exists(absolute_config_path):
        config_path = absolute_config_path
    elif not os.path.exists(config_path):
        # If not found at absolute path and not at relative path (CWD), warn and return
        LOGGER.warning(f"Config file not found at {absolute_config_path} or {config_path}. Using defaults.")
        return {}
    
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        LOGGER.error(f"Error loading config from {config_path}: {e}")
        return {}

def get_model(role: str = "default") -> LiteLlm:
    """
    Returns a LiteLlm instance configured for the specified role.
    Ensures the model is available in Ollama (pulls if missing).
    """
    # Ensure server is up
    start_ollama_server()

    config = load_config()
    models_config = config.get("models", {})
    
    # Get specific role config or fall back to default
    role_config = models_config.get(role, models_config.get("default", {}))
    
    model_name = role_config.get("name", DEFAULT_MODEL)
    provider = role_config.get("provider", DEFAULT_PROVIDER)
    context_length = role_config.get("context_length")
    
    # If the role is not 'default' and missing in config, fallback to default role's model if available,
    # otherwise use global default.
    if not role_config and role != "default":
         default_config = models_config.get("default", {})
         model_name = default_config.get("name", DEFAULT_MODEL)
         provider = default_config.get("provider", DEFAULT_PROVIDER)
         if context_length is None:
             context_length = default_config.get("context_length")

    # Ensure model is available
    # We only need to check availability for Ollama models
    if "ollama" in provider:
        # Extract clean model name if provider is part of the string passed to LiteLLM?
        # Actually LiteLLM takes "provider/model_name".
        # But ensure_model_available needs just the model name.
        # The config separates them, so we just pass model_name.
        try:
            ensure_model_available(model_name)
        except Exception as e:
            LOGGER.error(f"Failed to ensure model {model_name} is available: {e}")
            # We might still try to return the model object, or raise. 
            # If pull failed, LiteLLM will likely fail too.
            raise

    full_model_string = f"{provider}/{model_name}"
    LOGGER.info(f"Initializing LiteLlm with model: {full_model_string} for role: {role}")
    
    kwargs = {}
    if context_length:
        kwargs["num_ctx"] = context_length
    
    return LiteLlm(model=full_model_string, **kwargs)
