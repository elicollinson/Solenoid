# app/agent/planning_agent/dynamic_instruction.py
"""
Dynamic instruction generator for planning_agent.

This module generates the instruction prompt for planning_agent, incorporating
descriptions of all available agents (both static and custom) so the planner
knows what agents it can delegate to.
"""

import logging
from typing import Optional

from app.agent.config import get_agent_prompt
from app.agent.custom_agents.registry import get_registry

LOGGER = logging.getLogger(__name__)

# Template for agent descriptions in the instruction
AGENT_DESCRIPTION_TEMPLATE = """
- **{name}**: {description}
"""

# Section to inject into the planning agent prompt
CUSTOM_AGENTS_SECTION = """

## Custom Specialist Agents

In addition to the built-in agents, you have access to these custom specialist agents:

{agent_descriptions}

When a task matches one of these custom agents' expertise, delegate to them.
Custom agents have access to their own knowledge bases with domain-specific information.
"""


def get_custom_agents_section() -> str:
    """
    Generate the custom agents section for the planning instruction.

    Returns:
        Formatted string describing available custom agents, or empty string if none.
    """
    registry = get_registry()

    if not registry.is_initialized:
        LOGGER.debug("Registry not initialized, no custom agents section")
        return ""

    enabled_agents = registry.get_enabled_agents()

    if not enabled_agents:
        LOGGER.debug("No enabled custom agents")
        return ""

    agent_descriptions = []
    for agent in enabled_agents:
        desc = AGENT_DESCRIPTION_TEMPLATE.format(
            name=agent.name,
            description=agent.description,
        )
        agent_descriptions.append(desc.strip())

    section = CUSTOM_AGENTS_SECTION.format(
        agent_descriptions="\n".join(agent_descriptions)
    )

    LOGGER.info(f"Generated custom agents section with {len(enabled_agents)} agents")
    return section


def generate_planning_instruction(
    plan_state: str = "[]",
    session: Optional[any] = None,
) -> str:
    """
    Generate the complete planning agent instruction.

    This combines:
    1. The base planning prompt from app_settings.yaml
    2. Dynamic custom agents section
    3. Current plan state

    Args:
        plan_state: Current plan state JSON string
        session: Optional session for additional context

    Returns:
        Complete instruction string
    """
    # Get base prompt template
    base_prompt = get_agent_prompt("planning_agent")

    if not base_prompt:
        LOGGER.warning("No planning_agent prompt found in settings")
        base_prompt = "You are a planning agent that coordinates specialist agents."

    # Generate custom agents section
    custom_section = get_custom_agents_section()

    # Combine: insert custom section before the plan state placeholder
    # The base prompt should have {plan_state} placeholder
    if "{plan_state}" in base_prompt:
        # Insert custom agents section before the plan state
        full_prompt = base_prompt.replace(
            "{plan_state}",
            f"{custom_section}\n\n## Current Plan State\n{{plan_state}}"
        )
        # Now format with actual plan state
        full_prompt = full_prompt.format(plan_state=plan_state)
    else:
        # No placeholder, just append
        full_prompt = base_prompt + custom_section

    return full_prompt


def create_dynamic_instruction_callback():
    """
    Create a callback function for dynamic instruction generation.

    This returns a function compatible with ADK's instruction callback signature.
    """
    def dynamic_instruction_callback(*args, **kwargs):
        """
        Callback for generating dynamic planning instruction.

        Handles both old and new ADK callback signatures.
        """
        LOGGER.debug(f"dynamic_instruction_callback called with args={len(args)} kwargs={list(kwargs.keys())}")

        # Handle different call signatures
        context = None
        session = None

        if len(args) > 0:
            context = args[0]

        if hasattr(context, 'session'):
            session = context.session
        elif len(args) > 1:
            # Old signature: agent, session
            session = args[1]

        # Get plan state from session
        plan_state = "[]"
        if session and hasattr(session, 'state'):
            plan_state = session.state.get("plan", "[]")

        return generate_planning_instruction(plan_state=plan_state, session=session)

    return dynamic_instruction_callback
