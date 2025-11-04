"""
Local Responses service package.

Exposes a CLI via ``python -m local_responses`` and provides a FastAPI
application compatible with the OpenAI /v1/responses endpoint.
"""

from __future__ import annotations

__all__ = [
    "get_version",
]


def get_version() -> str:
    """Return the package version."""
    try:
        from importlib.metadata import version

        return version("local-general-agent")
    except Exception:  # pragma: no cover - metadata optional in dev installs
        return "0.1.0"

