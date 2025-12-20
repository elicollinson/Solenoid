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
    1. Check agent_models section for agent-specific config (e.g., "user_proxy_agent")
    2. Check models section for role-based config (e.g., "agent", "extractor")
    3. Fall back to models.default
    4. Fall back to hardcoded defaults
    """
    # Ensure server is up
    start_ollama_server()

    config = load_settings()
    agent_models_config = config.get("agent_models", {})
    models_config = config.get("models", {})

    # First, check if this is an agent-specific config
    role_config = agent_models_config.get(role)

    # If not found in agent_models, try the models section (for backward compatibility)
    if not role_config:
        role_config = models_config.get(role, models_config.get("default", {}))

    model_name = role_config.get("name", DEFAULT_MODEL)
    provider = role_config.get("provider", DEFAULT_PROVIDER)
    context_length = role_config.get("context_length")

    # If the role config is empty and role isn't 'default', fallback to default
    if not role_config and role != "default":
        default_config = models_config.get("default", {})
        model_name = default_config.get("name", DEFAULT_MODEL)
        provider = default_config.get("provider", DEFAULT_PROVIDER)
        if context_length is None:
            context_length = default_config.get("context_length")

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
