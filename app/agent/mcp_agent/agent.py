# app/agent/mcp_agent/agent.py
import logging
import os
import yaml
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters

LOGGER = logging.getLogger(__name__)

# Get the project root directory (this file is at app/agent/mcp_agent/agent.py)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, "../../../"))

# Debug callback to log tools before model is called
async def log_tools_before_model(callback_context, llm_request):
    """Debug callback to see what tools are available to the model."""
    LOGGER.info("=" * 60)
    LOGGER.info("[MCP_AGENT] === BEFORE MODEL CALLBACK ===")

    # Check config.tools (function declarations sent to model)
    config_tools = llm_request.config.tools if llm_request.config else []
    LOGGER.info(f"[MCP_AGENT] config.tools count: {len(config_tools) if config_tools else 0}")

    if config_tools:
        for i, tool in enumerate(config_tools):
            # tool here is a types.Tool with function_declarations
            func_decls = getattr(tool, 'function_declarations', [])
            LOGGER.info(f"[MCP_AGENT]   Tool {i+1} has {len(func_decls) if func_decls else 0} function_declarations")
            if func_decls:
                for fd in func_decls:
                    LOGGER.info(f"[MCP_AGENT]     - {fd.name}")
    else:
        LOGGER.error("[MCP_AGENT] !!! NO config.tools - MCP tools may not have been resolved !!!")

    # Check tools_dict (actual tool objects for execution)
    tools_dict = llm_request.tools_dict if hasattr(llm_request, 'tools_dict') else {}
    LOGGER.info(f"[MCP_AGENT] tools_dict has {len(tools_dict)} tools: {list(tools_dict.keys())}")

    if not tools_dict:
        LOGGER.error("[MCP_AGENT] !!! tools_dict is EMPTY - tool execution will fail !!!")

    LOGGER.info("=" * 60)
    return None  # Continue with normal processing

def load_mcp_toolsets_from_settings(settings_path="app_settings.yaml"):
    """Load MCP toolsets from the app_settings.yaml file.

    Supports two server types:
    - stdio: Launches a local process (requires 'command' and 'args')
    - http: Connects to a remote HTTP server (requires 'url', optional 'headers')
    """
    # Resolve the settings path relative to project root
    absolute_settings_path = os.path.join(_PROJECT_ROOT, settings_path)
    LOGGER.info(f"[MCP_AGENT] Loading settings from: {absolute_settings_path}")

    toolsets = []
    try:
        with open(absolute_settings_path, "r") as f:
            config = yaml.safe_load(f)

        if not config or "mcp_servers" not in config:
            LOGGER.warning(f"No 'mcp_servers' found in {settings_path}")
            return []

        for server_name, server_config in config["mcp_servers"].items():
            LOGGER.info(f"Loading MCP server: {server_name}")
            try:
                server_type = server_config.get("type", "stdio")

                if server_type == "http":
                    # HTTP-based MCP server (like context7)
                    url = server_config.get("url")
                    headers = server_config.get("headers", {})

                    if not url:
                        LOGGER.error(f"MCP server {server_name}: 'url' is required for http type")
                        continue

                    toolset = McpToolset(
                        connection_params=StreamableHTTPConnectionParams(
                            url=url,
                            headers=headers
                        )
                    )
                else:
                    # stdio-based MCP server (default)
                    command = server_config.get("command")
                    args = server_config.get("args", [])

                    if not command:
                        LOGGER.error(f"MCP server {server_name}: 'command' is required for stdio type")
                        continue

                    # Resolve relative paths in args to absolute paths
                    resolved_args = []
                    for arg in args:
                        if arg == "./" or arg == ".":
                            resolved_args.append(_PROJECT_ROOT)
                        elif arg.startswith("./"):
                            resolved_args.append(os.path.join(_PROJECT_ROOT, arg[2:]))
                        else:
                            resolved_args.append(arg)

                    toolset = McpToolset(
                        connection_params=StdioConnectionParams(
                            server_params=StdioServerParameters(
                                command=command,
                                args=resolved_args
                            )
                        )
                    )

                toolsets.append(toolset)
                LOGGER.info(f"Successfully loaded MCP toolset: {server_name} (type: {server_type})")
                LOGGER.info(f"Toolset object: {toolset}")

            except Exception as e:
                LOGGER.error(f"Failed to load MCP server {server_name}: {e}")

    except FileNotFoundError:
        LOGGER.warning(f"Settings file not found at {absolute_settings_path}")
    except Exception as e:
        LOGGER.error(f"Error loading MCP config: {e}")

    LOGGER.info(f"[MCP_AGENT] Total MCP toolsets loaded: {len(toolsets)}")
    return toolsets

from app.agent.config import get_agent_prompt

# Load prompt from settings
MCP_AGENT_PROMPT = get_agent_prompt("mcp_agent")

_mcp_toolsets = load_mcp_toolsets_from_settings()
LOGGER.info(f"[MCP_AGENT] Creating agent with {len(_mcp_toolsets)} toolsets")

# Note: The MCP toolsets are resolved at runtime when the agent runs.
# The before_model_callback will log what tools are available.

from app.agent.callbacks.memory import save_memories_on_final_response

mcp_agent = Agent(
    name="mcp_agent",
    model=get_model("mcp_agent"),
    instruction=MCP_AGENT_PROMPT,
    tools=_mcp_toolsets,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True,  # Agent must complete task, not transfer back
    before_model_callback=log_tools_before_model,
    # Memory storage on final response detection
    after_model_callback=[save_memories_on_final_response]
)
