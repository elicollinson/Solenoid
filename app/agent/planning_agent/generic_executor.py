# generic_executor.py
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
import yaml
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

LOGGER = logging.getLogger(__name__)

def load_mcp_toolsets(config_path="mcp_config.yaml"):
    """Load MCP toolsets from a YAML configuration file."""
    toolsets = []
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        if not config or "mcp_servers" not in config:
            LOGGER.warning(f"No 'mcp_servers' found in {config_path}")
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
        LOGGER.warning(f"MCP config file not found at {config_path}")
    except Exception as e:
        LOGGER.error(f"Error loading MCP config: {e}")
        
    return toolsets

# Define the Agent
agent = Agent(
    name="generic_executor_agent",
    model=get_model("agent"),
    instruction="""
    You are a Generic Executor Agent.
    
    YOUR GOAL: Execute general tasks, answer questions, and perform research or analysis as requested by the Planner.
    
    CAPABILITIES:
    - You can use available tools to find information or perform actions.
    - You can answer general knowledge questions.
    - You do NOT execute Python code or generate charts (those are for other specialists).
    
    OUTPUT:
    - Provide concise, direct answers to the Planner's specific request.
    - Do not ask follow-up questions unless absolutely necessary.

    ## IMPORTANT: ALWAYS TRANSFER YOUR RESULT TO YOUR PARENT AGENT IF EXECUTION IS COMPLETED.
    """,
    tools=load_mcp_toolsets(),
    disallow_transfer_to_peers=True
)

generic_executor_agent = agent
