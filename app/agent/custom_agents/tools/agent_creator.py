# app/agent/custom_agents/tools/agent_creator.py
"""
Agent creation workflow tools.

This module provides tools for a complete agent creation workflow:
1. plan_new_agent - Analyzes user request and creates a plan
2. research_for_agent - Searches and gathers sources for KB
3. finalize_agent - Creates the agent file and populates KB

The workflow is driven by the model with user approval checkpoints.
"""

import json
import logging
import re
import uuid
from typing import Optional

from google.adk.tools import FunctionTool

from app.agent.custom_agents.schema import CustomAgentSchema
from app.agent.custom_agents.loader import get_agents_directory, validate_agent_yaml
from app.agent.custom_agents.registry import get_registry
from app.agent.knowledge_base import ingest_url, ingest_text, get_kb_manager

LOGGER = logging.getLogger(__name__)


def plan_new_agent(
    user_request: str,
    proposed_name: str,
    proposed_description: str,
    proposed_instruction: str,
    research_topics: list[str],
    suggested_sources: list[str] = None,
) -> str:
    """
    Create a detailed plan for a new custom agent.

    Call this FIRST when a user asks to create a new agent. This creates a plan
    that the user must approve before proceeding.

    Args:
        user_request: The user's original request describing what agent they want.
        proposed_name: Suggested agent name (lowercase, underscores, e.g., "legal_research_agent").
        proposed_description: Short description of the agent's purpose (10-200 chars).
        proposed_instruction: Detailed system prompt for the agent.
        research_topics: List of topics to research for the agent's knowledge base.
                        These will be used to search for and gather relevant sources.
                        Example: ["contract law basics", "GDPR compliance", "legal terminology"]
        suggested_sources: Optional list of URLs to include in the knowledge base.
                          Leave empty if you want to search for sources.

    Returns:
        A formatted plan for user approval. The user MUST approve before proceeding.
    """
    # Validate name format
    if not re.match(r'^[a-z][a-z0-9_]*$', proposed_name):
        return (
            f"Error: Invalid agent name '{proposed_name}'. "
            "Name must start with a lowercase letter and contain only "
            "lowercase letters, numbers, and underscores."
        )

    # Check reserved names
    reserved = {
        "user_proxy_agent", "prime_agent", "planning_agent",
        "code_executor_agent", "chart_generator_agent",
        "research_agent", "generic_executor_agent", "mcp_agent",
    }
    if proposed_name in reserved:
        return f"Error: Name '{proposed_name}' is reserved for system agents."

    # Check if agent already exists
    registry = get_registry()
    if registry.has_agent(proposed_name):
        return f"Error: An agent named '{proposed_name}' already exists."

    # Check if file exists
    agents_dir = get_agents_directory()
    if (agents_dir / f"{proposed_name}.yaml").exists():
        return f"Error: Agent file already exists for '{proposed_name}'."

    suggested_sources = suggested_sources or []

    # Format the plan
    plan = f"""## Agent Creation Plan

### Agent Configuration
- **Name**: `{proposed_name}`
- **Description**: {proposed_description}

### System Instruction
```
{proposed_instruction}
```

### Knowledge Base Research Plan
The following topics will be researched to build the agent's knowledge base:

"""
    for i, topic in enumerate(research_topics, 1):
        plan += f"{i}. {topic}\n"

    if suggested_sources:
        plan += "\n### Pre-identified Sources\n"
        for url in suggested_sources:
            plan += f"- {url}\n"

    plan += """
### Tools Access
- `universal_search`: Web search capability
- `read_webpage`: Web page content extraction

### Next Steps
1. **Approve this plan** to proceed with agent creation
2. I will search for relevant sources on each topic
3. You can approve which sources to add to the knowledge base
4. The agent will be created and ready to use

**Do you approve this plan?** Reply with:
- "approved" or "yes" to proceed
- "modify" with changes you want
- "cancel" to abort
"""

    return plan


def execute_agent_research(
    agent_name: str,
    research_topics: list[str],
) -> str:
    """
    Execute research for an agent's knowledge base.

    Call this AFTER the user approves the plan. This searches for sources
    on each topic and returns URLs for the user to approve.

    Args:
        agent_name: The agent name from the approved plan.
        research_topics: The topics to research from the approved plan.

    Returns:
        A list of found sources for user approval.
    """
    # We'll use the search tool internally
    from app.agent.search.universal_search import universal_search

    all_sources = []

    results = f"## Research Results for {agent_name}\n\n"

    for topic in research_topics:
        results += f"### Topic: {topic}\n"

        try:
            search_results = universal_search(topic)
            # Parse the search results to extract URLs
            lines = search_results.split('\n')
            topic_sources = []

            for line in lines:
                if line.strip().startswith("Link:"):
                    url = line.replace("Link:", "").strip()
                    if url and url.startswith("http"):
                        topic_sources.append(url)
                        all_sources.append({"topic": topic, "url": url})

            if topic_sources:
                for url in topic_sources[:3]:  # Top 3 per topic
                    results += f"- {url}\n"
            else:
                results += "- No sources found\n"

        except Exception as e:
            results += f"- Search failed: {e}\n"

        results += "\n"

    if all_sources:
        results += f"""### Summary
Found {len(all_sources)} potential sources across {len(research_topics)} topics.

**Which sources should I add to the knowledge base?**
- Reply "all" to add all sources
- Reply with specific numbers (e.g., "1, 3, 5") to select specific sources
- Reply "none" to skip KB population
- Reply with custom URLs to add those instead

I'll then create the agent and populate its knowledge base with the approved sources.
"""
    else:
        results += """### No Sources Found
I couldn't find relevant sources through search.

**Options:**
- Provide specific URLs you want to include
- Reply "create anyway" to create the agent without initial KB content
- Reply "cancel" to abort
"""

    return results


def create_and_populate_agent(
    name: str,
    description: str,
    instruction: str,
    urls_to_ingest: list[str] = None,
    text_content: list[dict] = None,
) -> str:
    """
    Create the agent file and populate its knowledge base.

    Call this AFTER the user approves the sources. This is the final step
    that creates the agent and ingests content.

    Args:
        name: Agent name (must match the approved plan).
        description: Agent description.
        instruction: Agent system instruction.
        urls_to_ingest: List of approved URLs to add to the knowledge base.
        text_content: Optional list of {"title": str, "text": str} for direct text.

    Returns:
        Success or error message with next steps.
    """
    import yaml

    urls_to_ingest = urls_to_ingest or []
    text_content = text_content or []

    # Validate name again
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return f"Error: Invalid agent name '{name}'."

    # Build the agent config
    config = {
        "name": name,
        "description": description,
        "instruction": instruction,
        "tools": ["universal_search", "read_webpage"],
        "mcp_servers": [],
        "knowledge_base": {
            "enabled": True,
            "search_top_k": 10,
            "search_threshold": 0.7,
        },
        "metadata": {
            "author": "assistant",
            "version": 1,
            "tags": [],
        },
        "enabled": True,
    }

    # Validate the config
    try:
        schema = CustomAgentSchema(**config)
    except Exception as e:
        return f"Error: Invalid agent configuration: {e}"

    # Create the YAML file
    agents_dir = get_agents_directory()
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_file = agents_dir / f"{name}.yaml"

    try:
        yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)
        agent_file.write_text(yaml_content, encoding="utf-8")
        LOGGER.info(f"Created agent file: {agent_file}")
    except Exception as e:
        return f"Error: Failed to create agent file: {e}"

    # Reload agents to pick up the new one
    try:
        from app.agent.custom_agents.setup import reload_custom_agents
        from app.agent.planning_agent.agent import reload_custom_agents as update_planning

        new_agents, errors = reload_custom_agents()
        update_planning(new_agents)

        if errors:
            LOGGER.warning(f"Reload had errors: {errors}")
    except Exception as e:
        return f"Agent file created but reload failed: {e}"

    # Now populate the KB
    kb_results = []
    total_chunks = 0

    if urls_to_ingest:
        for url in urls_to_ingest:
            try:
                result = ingest_url(name, url)
                if result.success:
                    kb_results.append(f"✓ {result.title or url}: {result.chunk_count} chunks")
                    total_chunks += result.chunk_count
                else:
                    kb_results.append(f"✗ {url}: {result.error}")
            except Exception as e:
                kb_results.append(f"✗ {url}: {e}")

    if text_content:
        for item in text_content:
            try:
                result = ingest_text(name, item.get("text", ""), title=item.get("title"))
                if result.success:
                    kb_results.append(f"✓ {result.title}: {result.chunk_count} chunks")
                    total_chunks += result.chunk_count
                else:
                    kb_results.append(f"✗ {item.get('title', 'text')}: {result.error}")
            except Exception as e:
                kb_results.append(f"✗ {item.get('title', 'text')}: {e}")

    # Build success message
    message = f"""## Agent Created Successfully!

### Agent: `{name}`
{description}

### Configuration
- File: `agents/{name}.yaml`
- Tools: universal_search, read_webpage
- Knowledge Base: Enabled

"""

    if kb_results:
        message += f"""### Knowledge Base Population
{chr(10).join(kb_results)}

**Total**: {total_chunks} chunks ingested
"""
    else:
        message += """### Knowledge Base
No content ingested yet. You can add content by:
- Asking me to "add [URL] to {name}'s knowledge base"
- Providing documents or text to add
"""

    message += f"""
### Using Your New Agent
The agent is now available! Try asking questions in its domain and the
planning agent will delegate to `{name}` when appropriate.

To add more knowledge later:
- "Add [URL] to {name}'s knowledge base"
- "Search for [topic] and add to {name}'s KB"
"""

    return message


# Create FunctionTool instances
plan_new_agent_tool = FunctionTool(func=plan_new_agent)
execute_agent_research_tool = FunctionTool(func=execute_agent_research)
create_and_populate_agent_tool = FunctionTool(func=create_and_populate_agent)

__all__ = [
    "plan_new_agent",
    "plan_new_agent_tool",
    "execute_agent_research",
    "execute_agent_research_tool",
    "create_and_populate_agent",
    "create_and_populate_agent_tool",
]
