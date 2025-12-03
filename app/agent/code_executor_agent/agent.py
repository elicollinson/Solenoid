# agent_server.py
import logging
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from app.agent.models.factory import get_model
import yaml
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from app.agent.local_execution.adk_wrapper import ADKLocalWasmExecutor
from pathlib import Path
from google.genai import types

LOGGER = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
APP_ROOT = CURRENT_DIR.parent.parent.parent / "app"

# 2. Construct the path to the Wasm engine
WASM_PATH = APP_ROOT / "resources" / "python-wasi"

# 3. Initialize the Executor
# We convert it to string because Wasmtime usually expects a string path
secure_executor = ADKLocalWasmExecutor(wasm_path=str(WASM_PATH))

session_service = InMemorySessionService()

def kickstart_model(callback_context, llm_request):
    """
    INJECT A WAKE-UP COMMAND.
    This forces the model to treat the transfer as a 'START' signal.
    """
    if llm_request.contents:
        # We append a hidden instruction to the very end of the prompt
        steering_msg = (
            "\n\n[SYSTEM]: Control has been transferred to you. "
            "The user is waiting for the answer. "
            "WRITE THE PYTHON CODE IMMEDIATELY."
        )
        
        # Attach to the last message in the history
        last_msg = llm_request.contents[-1]
        if last_msg.parts:
            last_msg.parts.append(types.Part.from_text(text=steering_msg))

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

# 3. Define the Agent
agent = Agent(
    name="code_executor_agent",
    model=get_model("agent"),
    instruction="""
    You are a helpful assistant equipped with a Python Code Executor.
    
    REQUIREMENT:
    - Always use the code executor to run any code, do not attempt to execute code yourself.
    - ALWAYS Write Python code to solve logic/math problems, data processing, or any deterministic tasks.
    - YOU MUST invoke the code executor for ANY code you write.

    YOUR PROCESS:
    1. If the user asks a logic/math question, write Python code to solve it.
    2. The system will execute it and return the "COMMAND OUTPUT".
    3. CRITICAL: When the code correctly excecutes and you receive the output, STOP writing code. 
       Simply return the answer clearly based on the output.
    """,
    tools=load_mcp_toolsets(),
    before_model_callback=[kickstart_model],
    code_executor=secure_executor,
)

code_executor_agent = agent