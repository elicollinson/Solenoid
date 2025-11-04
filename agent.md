# Local General Agent Snapshot

- **Purpose**: Textual-based terminal UI that manages a local LLM (“local responses” service) and routes user prompts through an `openai-agents` graph with shell/settings tooling.

## Primary Libraries
- `textual` — renders the TUI (`local_general_agent.app.TerminalApp`).
- `openai` + `openai-agents` — async client + agent runtime (`AsyncOpenAI`, `Agent`, `Runner`, streaming events, SQLite session store).
- `sqlalchemy` — backing store used by `SQLiteSession` for conversation history.
- `huggingface_hub` & `mlx-lm` — pulled in by the bundled `local_responses` server to download/run Apple MLX-compatible checkpoints.
- `fastapi` + `uvicorn` — power the optional HTTP server exposed by `local_responses`.
- `typer` — lightweight CLI hook (dispatches `local_general_agent.main:main`).

## Core Modules
- `local_general_agent/app.py`
  - `TerminalApp`: main Textual application; handles slash commands, message log, and streaming assistant responses from `Runner.run_streamed`.
  - Manages spinner UI, markdown rendering, menu navigation, and integrates two sub-agents (`shell_agent`, `settings_agent`).
  - Controls the subprocess that runs `local_responses` (start/stop/restart, log capture, context window restarts). Command assembled via `_build_server_command()` and tuned by `LOCAL_RESPONSES_*` env vars.
- `local_general_agent/shell_agent.py`: constructs “Restricted Shell Assistant” with safe file/directory/read/write/search helpers and limited shell execution.
- `local_general_agent/settings_agent.py`: exposes “Settings Manager” agent with `list_settings` / `update_setting` tools that read/write the JSON config via callbacks into `TerminalApp`.
- `local_general_agent/config.py`: loads and persists `config/settings.json`, tracks `theme`, `context_window_tokens`, and extra keys.
- `local_general_agent/theme.py` + `resources/themes/`: resolves Solarized dark/light `.tcss` files applied at runtime.

## Runtime Flow
1. Entry: `local_general_agent.main:main` ⟶ `run_app()` creates `TerminalApp`.
2. On mount, the app (optionally) auto-starts the `local_responses` server using `uv run python -m local_responses ...` and opens/streams logs to `local_responses.log`.
3. User input:
   - Slash commands drive theme toggles, clearing history, menus, and settings.
   - Free-form prompts stream through the primary agent, which can hand off to the settings agent or call the shell tool; streamed deltas render live in the UI.
4. Settings changes persist to disk and immediately update the UI (themes) or restart the responses server (context window changes).

### Key Environment Variables
`LOCAL_RESPONSES_URL`, `LOCAL_RESPONSES_API_KEY`, `LOCAL_RESPONSES_AGENT_MODEL_ID`/`MODEL_ID`, `LOCAL_RESPONSES_AUTOSTART`, `LOCAL_RESPONSES_WORKSPACE_ROOT`, `LOCAL_RESPONSES_RUNNER`, `LOCAL_RESPONSES_MODEL`, `LOCAL_RESPONSES_MODEL_ID`, `LOCAL_RESPONSES_PORT`, `LOCAL_RESPONSES_EXTRA_ARGS`.

