# generic_executor.py
"""
Generic Executor Agent - Handles knowledge tasks and agent management.

This agent handles:
- Knowledge and text-based tasks
- Agent creation via agentic workflow (plan → research → create)
- Knowledge base population for custom agents
"""
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.callbacks.memory import save_memories_on_final_response
from app.agent.custom_agents.tools import (
    # Agent creation workflow (primary)
    plan_new_agent_tool,
    execute_agent_research_tool,
    create_and_populate_agent_tool,
    # Legacy tools
    propose_agent_tool,
    list_tools_tool,
    # Knowledge base
    add_url_to_kb_tool,
    add_text_to_kb_tool,
    search_kb_tool,
    get_kb_stats_tool,
    list_agents_with_kb_tool,
)

LOGGER = logging.getLogger(__name__)

# Load prompt from settings
GENERIC_EXECUTOR_PROMPT = get_agent_prompt("generic_executor_agent")

# Agent management and KB tools
AGENT_MANAGEMENT_TOOLS = [
    # Agent creation workflow (primary - use these for /create-agent)
    plan_new_agent_tool,
    execute_agent_research_tool,
    create_and_populate_agent_tool,
    # Legacy agent creation
    propose_agent_tool,
    list_tools_tool,
    # Knowledge base management
    add_url_to_kb_tool,
    add_text_to_kb_tool,
    search_kb_tool,
    get_kb_stats_tool,
    list_agents_with_kb_tool,
]

# Define the Agent
agent = Agent(
    name="generic_executor_agent",
    model=get_model("generic_executor_agent"),
    instruction=GENERIC_EXECUTOR_PROMPT,
    tools=AGENT_MANAGEMENT_TOOLS,
    # Memory storage on final response detection
    after_model_callback=[save_memories_on_final_response],
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True  # Agent must complete task, not transfer back
)

generic_executor_agent = agent
