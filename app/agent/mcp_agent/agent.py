# app/agent/mcp_agent/agent.py
import logging
import yaml
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

LOGGER = logging.getLogger(__name__)

def load_mcp_toolsets_from_settings(settings_path="app_settings.yaml"):
    """Load MCP toolsets from the app_settings.yaml file."""
    toolsets = []
    try:
        with open(settings_path, "r") as f:
            config = yaml.safe_load(f)
        
        if not config or "mcp_servers" not in config:
            LOGGER.warning(f"No 'mcp_servers' found in {settings_path}")
            return []

        for server_name, server_config in config["mcp_servers"].items():
            LOGGER.info(f"Loading MCP server: {server_name}")
            try:
                toolset = McpToolset(
                    connection_params=StdioConnectionParams(
                        server_params=StdioServerParameters(
                            command=server_config["command"],
                            args=server_config["args"]
                        )
                    )
                )
                toolsets.append(toolset)
            except Exception as e:
                LOGGER.error(f"Failed to load MCP server {server_name}: {e}")
                
    except FileNotFoundError:
        LOGGER.warning(f"Settings file not found at {settings_path}")
    except Exception as e:
        LOGGER.error(f"Error loading MCP config: {e}")
        
    return toolsets

MCP_AGENT_PROMPT = """
You are the MCP Integration Specialist. Your goal is to utilize the Model Context Protocol (MCP) tools available to you to assist the parent agent.

### YOUR CAPABILITIES
You have access to a set of MCP tools. These tools allow you to interact with external systems, such as the filesystem, databases, or other services.

### INSTRUCTIONS
1.  **Analyze** the user's request and the available tools.
2.  **Identify** which tools can help fulfill the request.
3.  **Invoke** the necessary tools with the appropriate arguments.
4.  **Report** the results back to your parent agent.

### IMPORTANT
-   If you cannot find a relevant tool, inform your parent agent.
-   Be precise with your tool arguments.
-   Always provide a summary of what you did and the results you obtained.
"""

mcp_agent = Agent(
    name="mcp_agent",
    model=get_model("agent"),
    instruction=MCP_AGENT_PROMPT,
    tools=load_mcp_toolsets_from_settings()
)
