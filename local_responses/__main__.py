"""Command line interface for the local responses service."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import uvicorn

from .app import create_app
from .config import DatabaseConfig, ModelConfig, ServiceConfig


cli = typer.Typer(help="Local Responses service commands.")


@cli.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind address."),
    port: int = typer.Option(4000, "--port", "-p", help="Port to listen on."),
    model: str = typer.Option(
        "google_adk",
        "--model",
        help="Backend name: google_adk, mlx_granite, llama_cpp, or litellm.",
    ),
    model_id: str = typer.Option("mlx_granite_4.0_h_tiny_4bit", "--model-id", help="Model identifier reported via /v1/models."),
    max_output_tokens: int = typer.Option(1024, "--max-output-tokens", help="Maximum tokens to generate per response."),
    temperature: float = typer.Option(0.7, "--temperature", help="Sampling temperature."),
    top_p: float = typer.Option(0.9, "--top-p", help=" nucleus sampling parameter."),
    context_window: int = typer.Option(16384, "--context-window", help="Context window token budget for trimming history (set to 0 to disable)."),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Require this API key for incoming requests."),
    db_path: Path = typer.Option(Path("local_responses.db"), "--db-path", help="SQLite database location."),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development only)."),
    log_level: str = typer.Option("info", "--log-level", help="Uvicorn log level."),
) -> None:
    """Serve the FastAPI application using uvicorn."""
    config = ServiceConfig(
        host=host,
        port=port,
        api_key=api_key,
        model=ModelConfig(
            backend=model,
            model_id=model_id,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            top_p=top_p,
            context_window_tokens=context_window if context_window > 0 else 0,
        ),
        database=DatabaseConfig(path=db_path),
        enable_llama_backend=model == "llama_cpp",
    )

    app = create_app(config)
    uvicorn.run(app, host=host, port=port, reload=reload, log_level=log_level)


def main() -> None:
    """Entrypoint executed via ``python -m local_responses``."""
    cli()


if __name__ == "__main__":
    main()
