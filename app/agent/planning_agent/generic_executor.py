# generic_executor.py
"""Generic Executor Agent - Handles knowledge and text-based tasks."""
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.callbacks.memory import save_memories_on_final_response

LOGGER = logging.getLogger(__name__)

# Load prompt from settings
GENERIC_EXECUTOR_PROMPT = get_agent_prompt("generic_executor_agent")

# Define the Agent
agent = Agent(
    name="generic_executor_agent",
    model=get_model("generic_executor_agent"),
    instruction=GENERIC_EXECUTOR_PROMPT,
    # Memory storage on final response detection
    after_model_callback=[save_memories_on_final_response],
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True  # Agent must complete task, not transfer back
)

generic_executor_agent = agent
