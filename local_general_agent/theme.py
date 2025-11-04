"""Theme utilities for the local_general_agent package."""

from __future__ import annotations

from pathlib import Path

THEME_DIR = Path(__file__).resolve().parent / "resources" / "themes"

THEMES: dict[str, str] = {
    "dark": "solarized_dark.tcss",
    "light": "solarized_light.tcss",
}

DEFAULT_THEME = "dark"


def available_themes() -> list[str]:
    """Return the list of available theme identifiers."""
    return sorted(THEMES.keys())


def get_theme_path(name: str) -> Path:
    """Resolve the CSS path for the supplied theme."""
    try:
        relative_path = THEMES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown theme: {name}") from exc

    path = THEME_DIR / relative_path
    if not path.exists():
        raise FileNotFoundError(
            f"Theme '{name}' should be at '{path}', but the file could not be found."
        )
    return path


def read_theme(name: str) -> str:
    """Return the CSS contents for a theme."""
    return get_theme_path(name).read_text()

