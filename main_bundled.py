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

# Suppress logging BEFORE any other imports to catch module-level logging setup
# This must be done early to prevent backend logs from appearing
logging.basicConfig(level=logging.ERROR, force=True)
logging.getLogger().setLevel(logging.ERROR)

# Now safe to import other modules
import signal
import threading
import time
from typing import Optional

import httpx
import uvicorn


# Configuration
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
HEALTH_CHECK_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
HEALTH_CHECK_TIMEOUT = 30  # seconds
HEALTH_CHECK_INTERVAL = 0.2  # seconds


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


class SilentUvicornServer:
    """
    Runs uvicorn server in a background thread with suppressed logging.
    """

    def __init__(self, app: str, host: str, port: int):
        self.app = app
        self.host = host
        self.port = port
        self.thread: Optional[threading.Thread] = None
        self._should_exit = False

    def start(self) -> None:
        """Start the server in a background thread."""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        """Run the uvicorn server (called in background thread)."""
        import asyncio

        # Ensure logging is suppressed in this thread too
        suppress_logging()

        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Configure and run uvicorn
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="error",  # Only show errors
                access_log=False,   # Disable access logs
                loop="asyncio",     # Use standard asyncio loop
            )
            server = uvicorn.Server(config)
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    def stop(self) -> None:
        """Signal the server to stop (handled by daemon thread)."""
        self._should_exit = True


def wait_for_backend(timeout: float = HEALTH_CHECK_TIMEOUT) -> bool:
    """
    Wait for the backend to become healthy.

    Args:
        timeout: Maximum time to wait in seconds

    Returns:
        True if backend is ready, False if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = httpx.get(HEALTH_CHECK_URL, timeout=1.0)
            if response.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(HEALTH_CHECK_INTERVAL)

    return False


def main() -> int:
    """
    Main entry point for the bundled application.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Suppress backend logging for clean frontend experience
    suppress_logging()

    # Start the backend server silently
    server = SilentUvicornServer(
        app="app.server.main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
    )
    server.start()

    # Wait for backend to be ready
    if not wait_for_backend():
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
