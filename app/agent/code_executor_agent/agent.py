# code_executor_agent/agent.py
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.local_execution.adk_wrapper import ADKLocalWasmExecutor
from pathlib import Path

LOGGER = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
APP_ROOT = CURRENT_DIR.parent.parent.parent / "app"

# Construct the path to the Wasm engine
WASM_PATH = APP_ROOT / "resources" / "python-wasi"

# Initialize the Executor
secure_executor = ADKLocalWasmExecutor(wasm_path=str(WASM_PATH))

# Load prompt from settings
CODE_EXECUTOR_PROMPT = get_agent_prompt("code_executor_agent")

# Define the Agent
agent = Agent(
    name="code_executor_agent",
    model=get_model("code_executor_agent"),
    instruction=CODE_EXECUTOR_PROMPT,
    code_executor=secure_executor,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True  # Agent must complete task, not transfer back
)

code_executor_agent = agent