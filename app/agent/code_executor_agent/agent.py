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



# 3. Define the Agent
agent = Agent(
    name="code_executor_agent",
    model=get_model("agent"),
    instruction="""
    You are a Python Code Executor Agent.
    
    YOUR GOAL: Solve the user's request using Python code.
    
    CRITICAL PROTOCOL:
    1.  RECEIVE REQUEST: Analyze the user's request.
    2.  WRITE CODE: Write Python code to solve it.
        - **IMPORTANT**: You MUST use `print()` to output the final result.
        - Variables not printed will NOT be visible to you.
        - Example: `print(result)`
    3.  WAIT FOR OUTPUT: The system will execute your code and return the result.
    4.  ANALYZE OUTPUT: Check the "COMMAND OUTPUT".
    5.  FINAL ANSWER: If the output is correct, use it to answer the user. DO NOT WRITE CODE AGAIN.
    
    STOPPING CONDITION:
    - If you see "COMMAND OUTPUT" in the history, you have ALREADY executed the code.
    - DO NOT re-execute the same code.
    - DO NOT write print statements to "see" the output again.
    - Just read the output from the history and give the final answer.

    ## IMPORTANT: ALWAYS TRANSFER YOUR RESULT TO YOUR PARENT AGENT IF EXECUTION IS COMPLETED.
    """,
    # tools=load_mcp_toolsets(),
    code_executor=secure_executor,
    disallow_transfer_to_peers=True
    
)

code_executor_agent = agent