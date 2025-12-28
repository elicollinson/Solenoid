# Configuration for internal app constants
from pathlib import Path

BACKEND_HOST = "127.0.0.1"
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
HOME_SETTINGS_PATH = Path.home() / "app_settings.yaml"


BACKEND_PORT = 8000
HEALTH_CHECK_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
HEALTH_CHECK_TIMEOUT = 30  # seconds
HEALTH_CHECK_INTERVAL = 0.2  # seconds