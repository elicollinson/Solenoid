from google.adk.models.lite_llm import LiteLlm
from app.agent.ollama.ollama_app import start_ollama_server

def get_granite_model() -> LiteLlm:
    start_ollama_server()
    return LiteLlm(model="ollama_chat/granite4:tiny-h")