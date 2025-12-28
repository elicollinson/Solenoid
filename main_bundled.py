"""
Bundled entry point for Local General Agent.

This script starts both the FastAPI backend (silently in background) and the
Textual frontend (in the main window) as a single executable application.

Usage:
    python main_bundled.py

Or via poetry:
    poetry run python main_bundled.py
    poetry run local-agent
"""

import logging
import sys
from pathlib import Path

# Suppress logging BEFORE any other imports to catch module-level logging setup
# This must be done early to prevent backend logs from appearing
logging.basicConfig(level=logging.ERROR, force=True)
logging.getLogger().setLevel(logging.ERROR)

# Now safe to import other modules
import json
import signal
import httpx


# Import the backend manager and actual FastAPI app object
# NOTE: The app must be imported directly (not as a string) for PyInstaller compatibility.
# Uvicorn's string-based imports like "app.server.main:app" use importlib internally,
# which fails in frozen executables because module paths don't exist on disk.
from app.server.manager import create_backend_server
from app.server.main import app as fastapi_app
from resources.default_settings import DEFAULT_SETTINGS
from resources.backend_config import BACKEND_HOST, OLLAMA_HOST, OLLAMA_PORT, HOME_SETTINGS_PATH, BACKEND_PORT, HEALTH_CHECK_URL, HEALTH_CHECK_TIMEOUT, HEALTH_CHECK_INTERVAL





# =============================================================================
# Pre-flight: Ollama and Model Management
# =============================================================================

def ensure_ollama_running() -> bool:
    """
    Ensure Ollama server is running. Starts it if needed.

    Returns:
        True if Ollama is running, False if failed to start
    """
    # Check if already running
    try:
        r = httpx.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=1.0)
        if r.status_code == 200:
            return True
    except:
        pass

    # Try to start Ollama using the app's existing logic
    try:
        from app.agent.ollama.ollama_app import start_ollama_server
        start_ollama_server(host=OLLAMA_HOST, port=OLLAMA_PORT)
        return True
    except Exception as e:
        print(f"Failed to start Ollama: {e}", file=sys.stderr)
        return False


def get_configured_model() -> str:
    """Get the model name from settings."""
    import yaml

    # Try local project settings first, then home directory fallback
    settings_paths = [Path("app_settings.yaml"), HOME_SETTINGS_PATH]

    for path in settings_paths:
        if path.exists():
            try:
                with open(path) as f:
                    config = yaml.safe_load(f) or {}
                    model_name = config.get("models", {}).get("default", {}).get("name")
                    if model_name:
                        return model_name
            except:
                pass

    # Fallback only if no settings file found
    return "ministral-3:8b"


def check_model_exists(model_name: str) -> bool:
    """Check if the model is already available in Ollama."""
    try:
        r = httpx.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=5.0)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return any(m.get("name") == model_name for m in models)
    except:
        pass
    return False


def pull_model_with_progress(model_name: str) -> bool:
    """
    Pull a model from Ollama with streaming progress display.

    Returns:
        True if successful, False otherwise
    """
    print(f"Downloading model '{model_name}'...")
    print("This may take several minutes depending on model size and connection speed.\n")

    url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/pull"

    try:
        # Use streaming to show progress
        with httpx.stream(
            "POST",
            url,
            json={"name": model_name, "stream": True},
            timeout=None,  # No timeout for large downloads
        ) as response:
            if response.status_code != 200:
                print(f"Error: Server returned {response.status_code}", file=sys.stderr)
                return False

            last_status = ""
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    status = data.get("status", "")

                    # Show download progress
                    if "total" in data and "completed" in data:
                        total = data["total"]
                        completed = data["completed"]
                        pct = (completed / total * 100) if total > 0 else 0
                        bar_len = 30
                        filled = int(bar_len * completed / total) if total > 0 else 0
                        bar = "█" * filled + "░" * (bar_len - filled)
                        size_mb = completed / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        print(f"\r  {status}: [{bar}] {pct:5.1f}% ({size_mb:.0f}/{total_mb:.0f} MB)", end="", flush=True)
                    elif status and status != last_status:
                        # Status changed, print on new line
                        if last_status:
                            print()  # End previous line
                        print(f"  {status}...", end="", flush=True)
                        last_status = status

                    # Check for completion
                    if status == "success":
                        print()  # End line
                        print(f"\nModel '{model_name}' ready!")
                        return True

                except json.JSONDecodeError:
                    continue

            print()  # End line
            return True

    except httpx.ConnectError:
        print(f"Error: Cannot connect to Ollama at {OLLAMA_HOST}:{OLLAMA_PORT}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"\nError downloading model: {e}", file=sys.stderr)
        return False


def ensure_model_ready() -> bool:
    """
    Pre-flight check: ensure Ollama is running and model is available.
    Shows progress during model download if needed.

    Returns:
        True if model is ready, False otherwise
    """
    print("Initializing Local Agent...")

    # Step 1: Ensure Ollama is running
    print("  Checking Ollama server...", end=" ", flush=True)
    if not ensure_ollama_running():
        print("FAILED")
        print("\nError: Could not start Ollama server.", file=sys.stderr)
        print("Please install Ollama from https://ollama.com/download", file=sys.stderr)
        return False
    print("OK")

    # Step 2: Check if model exists
    model_name = get_configured_model()
    print(f"  Checking model '{model_name}'...", end=" ", flush=True)

    if check_model_exists(model_name):
        print("OK")
        print()
        return True

    print("not found")
    print()

    # Step 3: Pull the model with progress
    if not pull_model_with_progress(model_name):
        print(f"\nError: Failed to download model '{model_name}'", file=sys.stderr)
        return False

    print()
    return True


# =============================================================================
# Settings and Logging
# =============================================================================

def ensure_settings_file() -> None:
    """Create default app_settings.yaml in home directory if it doesn't exist."""
    if not HOME_SETTINGS_PATH.exists():
        HOME_SETTINGS_PATH.write_text(DEFAULT_SETTINGS)


def suppress_logging() -> None:
    """Suppress noisy loggers for a clean terminal experience."""
    # Set root logger to ERROR
    logging.getLogger().setLevel(logging.ERROR)

    # Suppress uvicorn internal logs
    logging.getLogger("uvicorn").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)

    # Suppress FastAPI/app logs
    logging.getLogger("app").setLevel(logging.ERROR)
    logging.getLogger("app.server").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    # Suppress asyncio debug logs
    logging.getLogger("asyncio").setLevel(logging.ERROR)

    # Suppress AG-UI ADK logs
    logging.getLogger("ag_ui_adk").setLevel(logging.ERROR)
    logging.getLogger("ag_ui_adk.session_manager").setLevel(logging.ERROR)
    logging.getLogger("ag_ui_adk.event_translator").setLevel(logging.ERROR)

    # Suppress Google ADK logs
    logging.getLogger("google.adk").setLevel(logging.ERROR)
    logging.getLogger("google_genai").setLevel(logging.ERROR)

    # Suppress LiteLLM logs
    logging.getLogger("litellm").setLevel(logging.ERROR)
    logging.getLogger("LiteLLM").setLevel(logging.ERROR)


def main() -> int:
    """
    Main entry point for the bundled application.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Ensure settings file exists in home directory
    ensure_settings_file()

    # Pre-flight: ensure Ollama and model are ready BEFORE starting backend
    # This prevents the health check from timing out during model downloads
    if not ensure_model_ready():
        return 1

    # Suppress backend logging for clean frontend experience
    suppress_logging()

    # Start the backend server using the manager (enables restart from TUI)
    server = create_backend_server(
        app=fastapi_app,
        host=BACKEND_HOST,
        port=BACKEND_PORT,
    )
    server.start()

    # Wait for backend to be ready
    if not server.wait_for_ready():
        print("Error: Backend failed to start within timeout", file=sys.stderr)
        return 1

    # Set up signal handler for clean shutdown
    def signal_handler(signum, frame):
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Import and run the Textual frontend
        from app.ui.agent_app import AgentApp

        app = AgentApp(
            base_url=f"http://{BACKEND_HOST}:{BACKEND_PORT}",
            endpoint="/api/agent",
        )
        app.run()

    except KeyboardInterrupt:
        pass
    finally:
        # Clean shutdown
        server.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
