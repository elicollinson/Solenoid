# prime_agent/agent.py
"""
Prime Agent - The intelligent router of the agent system.

This agent decides whether requests can be answered directly or need delegation
to the planning system.
"""
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.callbacks.memory import save_memories_on_final_response
from app.agent.planning_agent.agent import planning_agent

LOGGER = logging.getLogger(__name__)


# Load prompt from settings
PRIME_AGENT_PROMPT = get_agent_prompt("prime_agent")

agent = Agent(
    name="prime_agent",
    model=get_model("prime_agent"),
    instruction=PRIME_AGENT_PROMPT,
    # Memory storage on final response detection
    after_model_callback=[save_memories_on_final_response],
    sub_agents=[planning_agent]
)