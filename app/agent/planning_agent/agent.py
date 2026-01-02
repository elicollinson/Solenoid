# planning_agent/agent.py
"""
Planning Agent - The coordinator that delegates to specialist agents.

This agent coordinates work between built-in specialist agents and
dynamically loaded custom agents from the agents/ directory.
"""
import logging
from typing import Optional
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.callbacks.memory import save_memories_on_final_response
from app.agent.code_executor_agent.agent import code_executor_agent
from app.agent.chart_generator_agent.agent import chart_generator_agent
from app.agent.research_agent.agent import research_agent
from app.agent.planning_agent.generic_executor import generic_executor_agent
from app.agent.mcp_agent.agent import mcp_agent
from app.agent.planning_agent.dynamic_instruction import create_dynamic_instruction_callback

LOGGER = logging.getLogger(__name__)

# Built-in specialist agents (always available)
BUILTIN_SUB_AGENTS = [
    code_executor_agent,
    chart_generator_agent,
    research_agent,
    generic_executor_agent,
    mcp_agent,
]

# Custom agents loaded dynamically (set during initialization)
_custom_agents: list[Agent] = []


def set_custom_agents(agents: list[Agent]) -> None:
    """
    Set the custom agents for the planning agent.

    This is called during server initialization after custom agents are loaded.
    """
    global _custom_agents
    _custom_agents = agents
    LOGGER.info(f"Planning agent configured with {len(agents)} custom agents")

    # Update the agent's sub_agents list
    if planning_agent:
        planning_agent._sub_agents = BUILTIN_SUB_AGENTS + _custom_agents
        LOGGER.info(
            f"Planning agent sub_agents updated: "
            f"{len(BUILTIN_SUB_AGENTS)} built-in + {len(_custom_agents)} custom"
        )


def get_all_sub_agents() -> list[Agent]:
    """Get all sub-agents (built-in + custom)."""
    return BUILTIN_SUB_AGENTS + _custom_agents


def reload_custom_agents(agents: list[Agent]) -> None:
    """
    Reload custom agents without restarting the server.

    This is called by the /reload-agents command handler.
    """
    global _custom_agents
    old_count = len(_custom_agents)
    _custom_agents = agents

    if planning_agent:
        planning_agent._sub_agents = BUILTIN_SUB_AGENTS + _custom_agents

    LOGGER.info(
        f"Custom agents reloaded: {old_count} -> {len(agents)} agents"
    )


# Create the dynamic instruction callback
dynamic_instruction = create_dynamic_instruction_callback()

# Define the Agent
# Note: sub_agents is initially just built-in agents
# Custom agents are added via set_custom_agents() during initialization
agent = Agent(
    name="planning_agent",
    model=get_model("planning_agent"),
    instruction=dynamic_instruction,
    # Memory storage on final response detection
    after_model_callback=[save_memories_on_final_response],
    sub_agents=BUILTIN_SUB_AGENTS,  # Custom agents added later
)

planning_agent = agent

