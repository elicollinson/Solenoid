# Configuration for internal app constants
import os
import platform
from pathlib import Path

BACKEND_HOST = "127.0.0.1"
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434

BACKEND_PORT = 8000
HEALTH_CHECK_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
HEALTH_CHECK_TIMEOUT = 30  # seconds
HEALTH_CHECK_INTERVAL = 0.2  # seconds


# =============================================================================
# Settings Path Resolution
# =============================================================================

def get_config_dir() -> Path:
    """
    Get the application config directory, creating it if needed.

    Uses platform-specific conventions:
    - macOS: ~/Library/Application Support/Solenoid/
    - Linux: ~/.config/solenoid/ (XDG standard)
    - Windows: %APPDATA%/Solenoid/
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        config_dir = Path.home() / "Library" / "Application Support" / "Solenoid"
    elif system == "Windows":
        config_dir = Path(os.environ.get("APPDATA", Path.home())) / "Solenoid"
    else:  # Linux and others - use XDG standard
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            config_dir = Path(xdg_config) / "solenoid"
        else:
            config_dir = Path.home() / ".config" / "solenoid"

    return config_dir


def get_settings_path() -> Path:
    """
    Get the settings file path.

    Resolution order:
    1. Local ./app_settings.yaml (for development)
    2. Platform-specific config directory (for installed apps)

    The config directory is created if it doesn't exist.
    """
    # Check for local development settings first
    local_settings = Path("app_settings.yaml")
    if local_settings.exists():
        return local_settings.resolve()

    # Use platform-specific config directory
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "settings.yaml"


def get_log_dir() -> Path:
    """
    Get the application log directory, creating it if needed.

    Uses platform-specific conventions:
    - macOS: ~/Library/Logs/Solenoid/
    - Linux: ~/.local/share/solenoid/logs/ or XDG_STATE_HOME
    - Windows: %LOCALAPPDATA%/Solenoid/Logs/
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        log_dir = Path.home() / "Library" / "Logs" / "Solenoid"
    elif system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        log_dir = Path(local_app_data) / "Solenoid" / "Logs"
    else:  # Linux and others
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            log_dir = Path(xdg_state) / "solenoid" / "logs"
        else:
            log_dir = Path.home() / ".local" / "state" / "solenoid" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


# Convenience functions for common paths
def get_settings_file() -> Path:
    """Alias for get_settings_path() for clarity."""
    return get_settings_path()


def get_log_file() -> Path:
    """Get the main application log file path."""
    return get_log_dir() / "solenoid.log"


# Legacy compatibility - these will be deprecated
# TODO: Remove after confirming all code uses the new functions
HOME_SETTINGS_PATH = get_settings_path()
