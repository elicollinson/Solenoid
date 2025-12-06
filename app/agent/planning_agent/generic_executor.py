# generic_executor.py
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt

LOGGER = logging.getLogger(__name__)

# Load prompt from settings
GENERIC_EXECUTOR_PROMPT = get_agent_prompt("generic_executor_agent")

# Define the Agent
agent = Agent(
    name="generic_executor_agent",
    model=get_model("agent"),
    instruction=GENERIC_EXECUTOR_PROMPT,
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True  # Agent must complete task, not transfer back
)

generic_executor_agent = agent
