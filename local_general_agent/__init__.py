"""A configurable terminal application with Solarized theming."""

from .app import TerminalApp, run_app
from .config import AppConfig, SearchConfig, load_config, save_config
from .theme import available_themes

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AppConfig",
    "SearchConfig",
    "TerminalApp",
    "available_themes",
    "load_config",
    "run_app",
    "save_config",
]
