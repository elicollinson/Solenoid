"""CLI entry point that launches the terminal application."""

from __future__ import annotations

from .app import run_app


def main() -> None:
    """Run the terminal application."""
    run_app()


if __name__ == "__main__":
    main()
