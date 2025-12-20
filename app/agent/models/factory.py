import logging
from google.adk.models.lite_llm import LiteLlm
from app.agent.ollama.ollama_app import start_ollama_server, ensure_model_available
from app.agent.config import load_settings
import litellm

LOGGER = logging.getLogger(__name__)

# Enable LiteLLM debug logging to see what's being sent to the model
# This will show the actual tools array being passed
litellm.set_verbose = True
# Uncomment below for even more detailed logging:
# litellm._turn_on_debug()

DEFAULT_MODEL = "granite4:tiny-h"
DEFAULT_PROVIDER = "ollama_chat"


def get_model(role: str = "default") -> LiteLlm:
    """
    Returns a LiteLlm instance configured for the specified role or agent name.
    Ensures the model is available in Ollama (pulls if missing).

    Resolution order:
    1. Check models.agents section for agent-specific config (e.g., "user_proxy_agent")
    2. Check models.agent for generic agent config
    3. Fall back to models.default
    4. Fall back to hardcoded defaults

    Each level inherits missing values from the next level in the chain.
    """
    # Ensure server is up
    start_ollama_server()

    config = load_settings()
    models_config = config.get("models", {})

    # Get the fallback configs
    default_config = models_config.get("default", {})
    agent_config = models_config.get("agent", {})
    agents_config = models_config.get("agents", {})

    # Build the effective config by merging in order: default -> agent -> agent-specific
    # Start with hardcoded defaults
    effective_config = {
        "name": DEFAULT_MODEL,
        "provider": DEFAULT_PROVIDER,
        "context_length": None,
    }

    # Apply default config
    for key in ["name", "provider", "context_length"]:
        if default_config.get(key) is not None:
            effective_config[key] = default_config[key]

    # For agent-specific roles (ending with _agent), apply agent config then agent-specific
    if role.endswith("_agent") or role in agents_config:
        # Apply models.agent config
        for key in ["name", "provider", "context_length"]:
            if agent_config.get(key) is not None:
                effective_config[key] = agent_config[key]

        # Apply agent-specific config from models.agents.<role>
        agent_specific = agents_config.get(role, {})
        for key in ["name", "provider", "context_length"]:
            if agent_specific.get(key) is not None:
                effective_config[key] = agent_specific[key]
    else:
        # For non-agent roles (e.g., "extractor"), check models.<role> directly
        role_config = models_config.get(role, {})
        for key in ["name", "provider", "context_length"]:
            if role_config.get(key) is not None:
                effective_config[key] = role_config[key]

    model_name = effective_config["name"]
    provider = effective_config["provider"]
    context_length = effective_config["context_length"]

    # Ensure model is available for Ollama models
    if "ollama" in provider:
        try:
            ensure_model_available(model_name)
        except Exception as e:
            LOGGER.error(f"Failed to ensure model {model_name} is available: {e}")
            raise

    full_model_string = f"{provider}/{model_name}"
    LOGGER.info(f"Initializing LiteLlm with model: {full_model_string} for role: {role}")

    kwargs = {}
    if context_length:
        kwargs["num_ctx"] = context_length

    return LiteLlm(model=full_model_string, **kwargs)
