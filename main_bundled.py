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
from resources.backend_config import (
    BACKEND_HOST, BACKEND_PORT,
    OLLAMA_HOST, OLLAMA_PORT,
    get_settings_path, get_config_dir, get_log_dir, get_log_file,
)




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
    """Get the model name from settings using unified path resolution."""
    import yaml

    settings_path = get_settings_path()
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                config = yaml.safe_load(f) or {}
                model_name = config.get("models", {}).get("default", {}).get("name")
                if model_name:
                    return model_name
        except:
            pass

    # Fallback only if no settings file found
    return "ministral-3:8b"


def get_configured_embedding_model() -> str:
    """Get the embedding model name from settings using unified path resolution."""
    import yaml

    settings_path = get_settings_path()
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                config = yaml.safe_load(f) or {}
                model_name = config.get("embeddings", {}).get("model")
                if model_name:
                    return model_name
        except:
            pass

    # Fallback to nomic-embed-text
    return "nomic-embed-text"


def check_model_exists(model_name: str) -> bool:
    """Check if the model is already available in Ollama.

    Handles both exact matches and tag variations (e.g., 'model' matches 'model:latest').
    """
    try:
        r = httpx.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=5.0)
        if r.status_code == 200:
            models = r.json().get("models", [])
            for m in models:
                name = m.get("name", "")
                # Exact match
                if name == model_name:
                    return True
                # Match without tag (e.g., 'nomic-embed-text' matches 'nomic-embed-text:latest')
                if name.startswith(model_name + ":"):
                    return True
                # Match if model_name includes a tag
                if model_name.startswith(name.split(":")[0] + ":"):
                    return True
            return False
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
    Pre-flight check: ensure Ollama is running and models are available.
    Shows progress during model download if needed.

    Returns:
        True if all models are ready, False otherwise
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

    # Step 2: Check if LLM model exists
    model_name = get_configured_model()
    print(f"  Checking LLM model '{model_name}'...", end=" ", flush=True)

    if check_model_exists(model_name):
        print("OK")
    else:
        print("not found")
        print()
        # Pull the LLM model with progress
        if not pull_model_with_progress(model_name):
            print(f"\nError: Failed to download model '{model_name}'", file=sys.stderr)
            return False

    # Step 3: Check if embedding model exists
    embedding_model = get_configured_embedding_model()
    print(f"  Checking embedding model '{embedding_model}'...", end=" ", flush=True)

    if check_model_exists(embedding_model):
        print("OK")
    else:
        print("not found")
        print()
        # Pull the embedding model with progress
        if not pull_model_with_progress(embedding_model):
            print(f"\nError: Failed to download embedding model '{embedding_model}'", file=sys.stderr)
            return False

    print()
    return True


# =============================================================================
# Settings and Logging
# =============================================================================

def ensure_settings_file() -> None:
    """Create default settings file if it doesn't exist.

    Also handles migration from old settings location (~/app_settings.yaml)
    to the new platform-specific location.
    """
    settings_path = get_settings_path()

    # Check for legacy settings at ~/app_settings.yaml and migrate if needed
    legacy_path = Path.home() / "app_settings.yaml"
    if legacy_path.exists() and not settings_path.exists():
        # Migrate legacy settings to new location
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(legacy_path.read_text())
        # Optionally remove the old file (or keep it as backup)
        # legacy_path.unlink()  # Uncomment to remove old file
        return

    if not settings_path.exists():
        # Ensure config directory exists
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(DEFAULT_SETTINGS)


def setup_file_logging() -> None:
    """Set up file-based logging to capture all app logs."""
    log_dir = get_log_dir()
    log_file = get_log_file()

    # Create a file handler that captures DEBUG and above
    file_handler = logging.FileHandler(log_file, mode='w')  # Overwrite each session
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Add file handler to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)  # Capture everything to file


def suppress_console_logging() -> None:
    """Suppress console output while keeping file logging active."""
    # Remove any existing console handlers and set root to only use file
    root_logger = logging.getLogger()

    # Create a NullHandler for console suppression
    # The file handler added by setup_file_logging() will still capture logs
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)

    # Add a NullHandler to prevent "No handler found" warnings
    # but actual logging goes to the file handler

    # Set console-only loggers to not propagate or use ERROR level for any new handlers
    console_loggers = [
        "uvicorn", "uvicorn.error", "uvicorn.access",
        "app", "app.server", "httpx", "httpcore", "asyncio",
        "ag_ui_adk", "ag_ui_adk.session_manager", "ag_ui_adk.event_translator",
        "google.adk", "google_genai", "litellm", "LiteLLM"
    ]

    for logger_name in console_loggers:
        logger = logging.getLogger(logger_name)
        # Remove stream handlers but keep file handlers
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)


VERSION = "1.2.6"

def main() -> int:
    """
    Main entry point for the bundled application.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Handle CLI flags before any heavy imports/operations
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("--version", "-V"):
            print(f"solenoid {VERSION}")
            return 0
        if arg in ("--help", "-h"):
            config_dir = get_config_dir()
            log_file = get_log_file()
            print(f"""solenoid {VERSION} - A localized AI agent for the terminal

Usage: solenoid [OPTIONS]

Options:
  -h, --help     Show this help message and exit
  -V, --version  Show version and exit
  --log          Show the application log from the last session

Solenoid starts a local AI agent with a terminal UI. It requires Ollama
to be installed and running for model inference.

Configuration: {config_dir}/settings.yaml
Log file:      {log_file}

For more information, visit: https://github.com/elicollinson/Solenoid
""")
            return 0
        if arg == "--log":
            log_file = get_log_file()
            if not log_file.exists():
                print(f"No app log found at {log_file}")
                print("Run solenoid at least once to generate logs.")
                return 1
            print(f"=== {log_file} ===\n")
            print(log_file.read_text())
            return 0

    # Ensure settings file exists
    ensure_settings_file()

    # Pre-flight: ensure Ollama and model are ready BEFORE starting backend
    # This prevents the health check from timing out during model downloads
    if not ensure_model_ready():
        return 1

    # Set up file logging to capture all app logs, then suppress console output
    setup_file_logging()
    suppress_console_logging()

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
    def signal_handler(_signum, _frame):
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
