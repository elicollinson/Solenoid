"""Basic sanity checks for theme configuration management."""

from __future__ import annotations

from local_general_agent import AppConfig, TerminalApp, load_config, save_config
from local_general_agent.theme import available_themes


def test_config_roundtrip() -> None:
    """Configuration writes should persist and be readable."""
    themes = available_themes()
    theme_set = set(themes)
    config = load_config(theme_set)
    original = config.theme

    # Choose an alternate theme if more than one is available.
    new_theme = next((theme for theme in themes if theme != original), original)
    config.theme = new_theme
    save_config(config)

    reloaded = load_config(theme_set)
    assert reloaded.theme == new_theme

    # Restore original value to avoid side effects for local development.
    config.theme = original
    save_config(config)

def test_apply_theme_updates_state() -> None:
    """Switching themes should update the app and persist preference."""
    app = TerminalApp()
    original = app.config.theme
    try:
        for theme in available_themes():
            app.apply_theme(theme)
            assert app.theme_name == theme
    finally:
        app.apply_theme(original)


if __name__ == "__main__":
    test_config_roundtrip()
    test_apply_theme_updates_state()
