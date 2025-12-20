# chart_generator_agent/agent.py
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
CHART_GENERATOR_PROMPT = get_agent_prompt("chart_generator_agent")

# Define the Agent
agent = Agent(
    name="chart_generator_agent",
    model=get_model("chart_generator_agent"),
    instruction=CHART_GENERATOR_PROMPT,
    code_executor=secure_executor,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True  # Agent must complete task, not transfer back
)

chart_generator_agent = agent
