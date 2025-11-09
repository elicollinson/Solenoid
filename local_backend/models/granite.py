from google.adk.models import LiteLLM
from local_backend.ollama.ollama_app import start_ollama_server

def get_granite_model() -> LiteLLM:
    start_ollama_server()
    return LiteLLM(name="ollama_chat/granite4:tiny-h")