# app/server/manager.py
"""
Backend server manager for controlling the uvicorn server lifecycle.

This module provides a singleton manager that allows the TUI to
request backend restarts when settings change.
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Callable, Any
from resources.backend_config import BACKEND_HOST, BACKEND_PORT, HEALTH_CHECK_INTERVAL, HEALTH_CHECK_TIMEOUT, HEALTH_CHECK_URL

import httpx
import uvicorn

LOGGER = logging.getLogger(__name__)

class BackendServer:
    """
    Manages a uvicorn server in a background thread with restart capability.

    IMPORTANT - PyInstaller Compatibility:
    The `app` parameter MUST be the actual ASGI application object, NOT a string
    like "app.server.main:app". Uvicorn uses importlib.import_module() internally
    to resolve string references, which fails in frozen PyInstaller executables.
    """

    def __init__(self, app: Any, host: str, port: int):
        self.app = app  # Must be actual ASGI app object, not a string path
        self.host = host
        self.port = port
        self.thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._restart_callbacks: list[Callable[[], None]] = []

    def add_restart_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback to be called when restart completes."""
        self._restart_callbacks.append(callback)

    def remove_restart_callback(self, callback: Callable[[], None]) -> None:
        """Remove a restart callback."""
        if callback in self._restart_callbacks:
            self._restart_callbacks.remove(callback)

    def start(self) -> None:
        """Start the server in a background thread."""
        with self._lock:
            if self.thread and self.thread.is_alive():
                LOGGER.warning("Server already running")
                return

            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _suppress_logging(self) -> None:
        """Suppress noisy loggers for a clean terminal experience."""
        logging.getLogger().setLevel(logging.ERROR)
        for logger_name in [
            "uvicorn", "uvicorn.error", "uvicorn.access",
            "app", "app.server", "httpx", "httpcore", "asyncio",
            "ag_ui_adk", "ag_ui_adk.session_manager", "ag_ui_adk.event_translator",
            "google.adk", "google_genai", "litellm", "LiteLLM"
        ]:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

    def _run(self) -> None:
        """Run the uvicorn server (called in background thread)."""
        self._suppress_logging()

        # Create a new event loop for this thread
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="error",
                access_log=False,
                loop="asyncio",
            )
            self._server = uvicorn.Server(config)
            self._loop.run_until_complete(self._server.serve())
        except Exception as e:
            LOGGER.error(f"Server error: {e}")
        finally:
            self._loop.close()
            self._server = None
            self._loop = None

    def stop(self) -> bool:
        """
        Stop the server gracefully.

        Returns:
            True if stopped successfully, False otherwise
        """
        with self._lock:
            if not self._server or not self._loop:
                return True

            try:
                # Signal the server to exit
                self._server.should_exit = True

                # Wait for thread to finish
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=5.0)

                return not (self.thread and self.thread.is_alive())
            except Exception as e:
                LOGGER.error(f"Error stopping server: {e}")
                return False

    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self.thread is not None and self.thread.is_alive()

    def wait_for_ready(self, timeout: float = HEALTH_CHECK_TIMEOUT) -> bool:
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

    def restart(self) -> bool:
        """
        Restart the server.

        Returns:
            True if restart was successful, False otherwise
        """
        LOGGER.info("Restarting backend server...")

        # Stop the current server
        if not self.stop():
            LOGGER.error("Failed to stop server for restart")
            return False

        # Wait a moment for port to be released
        time.sleep(0.5)

        # Clear any cached settings/modules that need reloading
        self._clear_caches()

        # Start the server again
        self.start()

        # Wait for it to be ready
        if not self.wait_for_ready():
            LOGGER.error("Server failed to become ready after restart")
            return False

        LOGGER.info("Backend server restarted successfully")

        # Notify callbacks
        for callback in self._restart_callbacks:
            try:
                callback()
            except Exception as e:
                LOGGER.error(f"Restart callback error: {e}")

        return True

    def _clear_caches(self) -> None:
        """Clear cached settings and modules that need reloading."""
        try:
            from app.agent.config import clear_settings_cache
            clear_settings_cache()
        except ImportError:
            pass


# Global singleton instance
_server: Optional[BackendServer] = None


def get_backend_server() -> Optional[BackendServer]:
    """Get the global backend server instance (if running in bundled mode)."""
    return _server


def set_backend_server(server: BackendServer) -> None:
    """Set the global backend server instance."""
    global _server
    _server = server


def create_backend_server(
    app: Any,
    host: str = BACKEND_HOST,
    port: int = BACKEND_PORT
) -> BackendServer:
    """
    Create and register a new backend server.

    Args:
        app: The ASGI app object (must be actual object, not a string path)
        host: Host to bind to
        port: Port to bind to

    Returns:
        The created BackendServer instance
    """
    global _server
    _server = BackendServer(app=app, host=host, port=port)
    return _server
