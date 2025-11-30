# Terminal App - Solarized Edition

A modern terminal application with Solarized theming and slash command menu support built with Python and Textual.

## Features

- **Bordered Text Input**: Beautiful input box with rounded borders that properly display while typing
- **Slash Commands**: Type `/` to access various menu commands with interactive navigation
- **Keyboard Navigation**: Navigate menus with arrow keys, Enter, and Esc
- **Solarized Themes**: Authentic Solarized color palette for both light and dark modes - affects all colors, borders, and accents
- **Context Compaction**: Automatically condense older turns into a structured memory snapshot when the chat nears the model's token budget—no extra memory service required
- **Persistent Settings**: Last selected theme is saved to `local_general_agent/config/settings.json`
- **Full-Screen TUI**: Modern text-based UI using Textual framework with Rich formatting
- **Smooth Experience**: No color block artifacts or border issues

### When Does Context Compaction Run?

Compaction is governed by the `model.compaction` settings (see `local_responses/config.py`). The key dials are:

- **trigger_ratio** – the compactor wakes up once the tokenizer-estimated prompt tokens exceed `trigger_ratio × context_window_tokens` (always respecting `limits.hard_tokens`). Defaults to `0.75`, so a 16k window compacts near ~12k tokens.
- **min_history_messages** – avoids summarizing tiny conversations. Nothing happens until at least this many messages exist (default `8`).
- **preserve_recent_messages** – the newest N turns are never dropped, even if the compactor suggests trimming them (default `4`).
- **limits.* fields** – `target_tokens`, `hard_tokens`, and the max counts for notes/anchors bound the compactor’s own JSON output so it can fit back into the context for small models.

Each time those conditions are met the service asks the current model to emit a structured snapshot, persists it in SQLite, removes any safe-to-drop rows, and inserts a succinct system message summarizing the prior discussion.

## Installation

This project uses `poetry` for dependency management:

```bash
# Install dependencies (creates the virtual environment)
poetry install

# Run the application
poetry run python -m local_general_agent.main
```

## Usage

### Running the App

```bash
poetry run python -m local_general_agent.main
```

### Built-in Commands

- `/theme [name]` - Toggle themes or switch to a specific theme (`dark`, `light`)
- `/clear` - Clear the screen
- `/commands` - List all available commands
- `exit`, `quit`, or `q` - Exit the application

### Menu Commands

- `/settings` - Open the hierarchical settings menu (theme selection)
- `/help` - Get help (commands, shortcuts, about)
- `/tools` - Access tools (calculator, converter, formatter)

### Settings Navigation

Use the arrow keys to move between items, press **Enter** or the space bar to apply a setting, and press **Esc** to return to the previous menu.

### Keyboard Shortcuts

- **Arrow Keys**: Navigate menus
- **Enter**: Select menu item
- **Esc**: Cancel/exit menu
- **Ctrl+C** or **Ctrl+D**: Exit application
- **Tab**: Auto-complete commands
- **Up/Down**: Navigate command history

## Architecture

The application is built with Textual, a modern Python framework for building terminal user interfaces:

### Project Structure

```
local_general_agent/
├── __init__.py            # Package export surface
├── app.py                 # Textual TerminalApp and screens
├── config.py              # Config dataclass and helpers
├── config/
│   └── settings.json      # Persisted user settings
├── resources/
│   └── themes/
│       ├── solarized_dark.tcss
│       └── solarized_light.tcss
├── theme.py               # Theme lookup utilities
└── main.py                # CLI wrapper calling run_app()
```

### Key Components

#### Textual App (`app.py`)

The main application class inheriting from Textual's `App`:

```python
from local_general_agent import AppConfig, TerminalApp

# Create and run app with a preferred theme
config = AppConfig(theme="light")
app = TerminalApp(config=config)
app.run()
```

#### Solarized Themes (`.tcss` files)

Textual uses CSS-like syntax for styling. The themes are defined in:
- `solarized_dark.tcss` - Dark theme with authentic Solarized colors
- `solarized_light.tcss` - Light theme with authentic Solarized colors

Example CSS styling:
```css
/* Input widget with border */
Input {
    border: round $foreground-muted;
    background: $background-lighten-1;
    color: $foreground;
}

Input:focus {
    border: round $blue;
}
```

#### Menu Screens

Interactive menus using Textual's `OptionList` widget:

```python
# Creating a menu is simple
self.show_menu("Settings", [
    ("theme", "Theme - Switch between available themes"),
    ("display", "Display - Adjust display settings"),
    ("advanced", "Advanced - Advanced configuration options"),
])
```

## Customization Examples

### Enabling Phoenix Telemetry (Local Docker)

If you're running Arize Phoenix locally via Docker (default container exposes gRPC on `http://localhost:4317`), add the following snippet to `local_general_agent/config/settings.json` to enable tracing when the Terminal app launches the bundled `local_responses` service:

```json
{
  "theme": "light",
  "context_window_tokens": 16384,
  "telemetry": {
    "enabled": true,
    "endpoint": "http://localhost:4317",
    "protocol": "grpc",
    "project_name": "local-responses",
    "batch": true,
    "auto_instrument": false,
    "verbose": false,
    "api_key_env": "PHOENIX_API_KEY"
  }
}
```

If Phoenix is running without authentication, no API key is necessary; otherwise set `PHOENIX_API_KEY` in your environment before launching the app.

### Google ADK Conversational Backend

The bundled `local_responses` service now defaults to the `google_adk` backend so every chat turn is handled by a Google Agent Development Kit (ADK) conversational agent instead of a single raw model call. The agent uses ADK’s [`LiteLlm` model adapter](https://github.com/google/adk-python/blob/main/contributing/samples/hello_world_ollama/README.md) under the hood, so you can keep running the same Granite model by pointing LiteLLM at your preferred runtime (Ollama, MLX HTTP bridge, Vertex, etc.).

1. Start the terminal app as usual – it will autostart `local_responses` with `LOCAL_RESPONSES_MODEL=google_adk`.
2. Export the LiteLLM-compatible environment variables for your Granite deployment. For example, if you expose `granite4:tiny-h` through Ollama’s OpenAI bridge:

```bash
export LOCAL_RESPONSES_MODEL_ID="granite4:tiny-h"
export OPENAI_API_BASE="http://localhost:11434/v1"
export OPENAI_API_KEY="local-demo-key"
```

You can use `OLLAMA_API_BASE` or any other LiteLLM knobs in the same way described in the ADK docs.

> ℹ️ The ADK agent keeps conversation state per `conversation_id`, so each Terminal UI tab maps to its own ADK session automatically—no extra setup required.

### Local Hybrid Memory for ADK

When the Google ADK backend is selected the service now boots a local memory stack (`memories.db`) that runs entirely on SQLite + FTS5 + [sqlite-vec](https://alexgarcia.xyz/sqlite-vec/):

- **Persistence:** profile, episodic, and semantic memories live in `memory/schema.sql` (with triggers that mirror rows into FTS5 and vec0 virtual tables).
- **Local embeddings:** `memory/embeddings.py` loads `nomic-ai/nomic-embed-text-v1.5` through `sentence-transformers`, applies the Matryoshka 256D crop, and writes sqlite-vec blobs—no external embedding API or Ollama required.
- **Hybrid retrieval:** `memory/search.py` combines sqlite-vec ANN (distance) + FTS5 BM25 via Reciprocal Rank Fusion and reranks with BGE v2 m3 (`FlagEmbedding`).
- **ADK tools:** the agent automatically receives `PreloadMemoryTool` + `load_memory`, powered by `SqliteMemoryService`, so it can recall facts each turn. You can point the store at a different path with `python -m local_responses --memory-db-path /path/to/mem.db`.
- **Memory agent + tools:** import `memory.memory_tools` to access `store_memory`, `retrieve_memory`, and the dedicated `memory_agent` if you want a specialized agent that other ADK agents can call through function tools.

Everything runs locally on macOS (M3+) as long as the dependencies listed in the “Implementation Prompt” are installed (torch, sentence-transformers, sqlite-vec, FlagEmbedding, numpy). If your system Python cannot load extensions, install `pysqlite3-binary` and set `PYTHONPATH` accordingly.

### Model Context Protocol (MCP) Support

The agent supports the Model Context Protocol (MCP), allowing you to dynamically extend its capabilities with external tools. You can configure MCP servers using a `mcp_config.yaml` file in the root of the repository.

#### Configuration

Create a `mcp_config.yaml` file in the project root. The file should define the MCP servers you want to connect to.

**Example `mcp_config.yaml`:**

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "./"
```

In this example:
- `filesystem` is the name of the server (used for logging).
- `command` is the executable to run (e.g., `npx`, `python`).
- `args` is a list of arguments to pass to the command.

#### How it Works

When the agent starts, it checks for `mcp_config.yaml`. If found, it initializes the configured MCP servers and adds their tools to the agent's toolset. This allows the agent to use these tools seamlessly during conversations.

For example, with the filesystem server configured above, the agent can use tools like `list_directory` and `read_file` to interact with your local files.

### Extending the App

You can extend the `TerminalApp` class to add custom functionality:

```python
from local_general_agent import AppConfig, TerminalApp

class MyCustomApp(TerminalApp):
    def handle_slash_command(self, text: str) -> None:
        """Override to add custom commands."""
        command_parts = text[1:].split()
        command = command_parts[0].lower() if command_parts else ""

        if command == "custom":
            self.add_message("success", "Custom command executed!")
        else:
            # Fall back to default handler
            super().handle_slash_command(text)

# Run your custom app
config = AppConfig(theme="dark")
app = MyCustomApp(config=config)
app.run()
```

### Adding Custom CSS Styling

Create your own theme by modifying the `.tcss` files:

```css
/* custom_theme.tcss */
$background: #1a1a1a;
$foreground: #00ff00;  /* Matrix green! */

Input {
    border: heavy $foreground;
    color: $foreground;
}
```

### Adding New Menu Screens

```python
# Add to your extended app
def show_custom_tools(self):
    self.show_menu("My Tools", [
        ("tool1", "Tool 1 - Description"),
        ("tool2", "Tool 2 - Description"),
    ])

# Call it from a slash command
if command == "mytools":
    self.show_custom_tools()
```

## Color Palette

### Solarized Dark

- Background: `#002b36` (base03)
- Highlights: `#073642` (base02)
- Content: `#839496` (base0)
- Emphasized: `#93a1a1` (base1)

### Solarized Light

- Background: `#fdf6e3` (base3)
- Highlights: `#eee8d5` (base2)
- Content: `#657b83` (base0)
- Emphasized: `#586e75` (base1)

### Accent Colors (Both Themes)

- Yellow: `#b58900`
- Orange: `#cb4b16`
- Red: `#dc322f`
- Magenta: `#d33682`
- Violet: `#6c71c4`
- Blue: `#268bd2`
- Cyan: `#2aa198`
- Green: `#859900`

## Development

### Requirements

- Python 3.10+
- Poetry (for dependency management)

### Dependencies

- textual >= 0.47.0 (includes Rich for formatting)

## License

This is a demonstration project for building configurable terminal applications.

## Why Textual?

Textual provides several advantages over other terminal UI libraries:
- **Native widget support** with proper borders that work correctly
- **CSS-like styling** system for easy theming
- **Rich integration** for beautiful text formatting
- **Modern architecture** with reactive programming
- **Cross-platform** support (terminal and web browser)

## Credits

- Color scheme based on [Solarized](https://ethanschoonover.com/solarized/)
- Built with [Textual](https://github.com/textualize/textual)
- Rich formatting from [Rich](https://github.com/Textualize/rich)

## Model Configuration

The application allows you to configure which models are used for different roles (agent, memory extractor, etc.) via a YAML configuration file.

### Configuration File

Create a file named `app_settings.yaml` in the root directory of the project. If this file is not present, the application defaults to using `granite4:tiny-h` for all roles.

**Example `app_settings.yaml`:**

```yaml
models:
  default:
    name: "granite4:tiny-h"
    provider: "ollama_chat"
  agent:
    name: "granite4:tiny-h"
    # provider defaults to "ollama_chat" if not specified
  extractor:
    name: "granite4:tiny-h"
```

### Model Requirements

The models used for the **agent** role must support **function calling** (tool use). This is critical because the agent relies on tools to interact with the memory system and other extensions.

- **Recommended Models**: `granite4:tiny-h`, `llama3.1`, `mistral-nemo`, or other models known to have strong function calling capabilities.
- **Ollama Names**: Use the exact model name as it appears in the [Ollama library](https://ollama.com/library).

### Automatic Model Pulling

If a configured model is not found in your local Ollama instance, the application will automatically attempt to pull it when the agent starts. This ensures that the required models are always available without manual intervention.
