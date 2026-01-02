# app/agent/custom_agents/tools/propose_agent.py
"""
Tool for proposing new custom agents.

This FunctionTool allows the model to draft agent specifications
that can then be reviewed and approved by the user.

The workflow:
1. User asks for a new agent (e.g., "create an agent for legal research")
2. Model uses propose_agent tool to draft the specification
3. Response includes the proposed YAML
4. User reviews and can modify before saving
5. Once approved, agent file is created and agents are reloaded
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Optional

from google.adk.tools import FunctionTool

from app.agent.custom_agents.schema import CustomAgentSchema
from app.agent.custom_agents.loader import get_agents_directory, validate_agent_yaml
from app.agent.custom_agents.registry import get_registry

LOGGER = logging.getLogger(__name__)


def propose_agent(
    name: str,
    description: str,
    instruction: str,
    tools: list[str] = None,
    mcp_servers: list[str] = None,
    enable_knowledge_base: bool = True,
) -> str:
    """
    Propose a new custom agent specification.

    This tool creates a draft agent configuration that the user can review
    and approve. The agent will be saved to the agents/ directory.

    Args:
        name: Unique identifier for the agent (lowercase, underscores allowed).
              Must start with a letter and not conflict with system agents.
              Example: "legal_research_agent"
        description: Brief description of the agent's purpose (10-500 chars).
                     This helps the planning agent decide when to delegate.
                     Example: "Specializes in legal document analysis and contract review"
        instruction: Detailed system prompt for the agent (min 20 chars).
                     Should include the agent's role, responsibilities, and guidelines.
                     Example: "You are an expert legal researcher. When analyzing documents..."
        tools: List of tools the agent can use. Available tools:
               - universal_search: Web search via Brave API
               - read_webpage: Fetch and parse web pages
               Leave empty for an agent that only uses its knowledge base.
        mcp_servers: List of MCP servers the agent can access.
                     Must be configured in app_settings.yaml.
                     Example: ["filesystem"]
        enable_knowledge_base: Whether to enable a knowledge base for this agent.
                               If true, the agent gets isolated KB tables for RAG.
                               Default: true

    Returns:
        A message with the proposed agent YAML configuration.
        The user should review this before confirming creation.
    """
    # Validate name format
    import re
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return (
            f"Error: Invalid agent name '{name}'. "
            "Name must start with a lowercase letter and contain only "
            "lowercase letters, numbers, and underscores."
        )

    # Check for reserved names
    reserved = {
        "user_proxy_agent", "prime_agent", "planning_agent",
        "code_executor_agent", "chart_generator_agent",
        "research_agent", "generic_executor_agent", "mcp_agent",
    }
    if name in reserved:
        return f"Error: Agent name '{name}' is reserved for system agents."

    # Check if agent already exists
    registry = get_registry()
    if registry.has_agent(name):
        return f"Error: An agent named '{name}' already exists."

    # Check if file already exists
    agents_dir = get_agents_directory()
    agent_file = agents_dir / f"{name}.yaml"
    if agent_file.exists():
        return f"Error: Agent file already exists at {agent_file.name}"

    # Validate description and instruction
    if len(description) < 10:
        return "Error: Description must be at least 10 characters."
    if len(description) > 500:
        return "Error: Description must be at most 500 characters."
    if len(instruction) < 20:
        return "Error: Instruction must be at least 20 characters."

    # Build the agent config
    tools = tools or []
    mcp_servers = mcp_servers or []

    # Validate tools
    available_tools = {"universal_search", "read_webpage"}
    invalid_tools = set(tools) - available_tools
    if invalid_tools:
        return (
            f"Error: Unknown tools: {invalid_tools}. "
            f"Available tools: {available_tools}"
        )

    # Build YAML config
    config = {
        "name": name,
        "description": description,
        "instruction": instruction,
        "tools": tools,
        "mcp_servers": mcp_servers,
        "knowledge_base": {
            "enabled": enable_knowledge_base,
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

    # Validate with schema
    try:
        schema = CustomAgentSchema(**config)
    except Exception as e:
        return f"Error: Invalid agent configuration: {e}"

    # Generate YAML output
    yaml_output = yaml.dump(config, default_flow_style=False, sort_keys=False)

    # Format response
    response = f"""## Proposed Agent: {name}

I've drafted the following agent configuration:

```yaml
{yaml_output}```

### Summary:
- **Name**: {name}
- **Description**: {description}
- **Tools**: {', '.join(tools) if tools else 'None (KB-only)'}
- **MCP Servers**: {', '.join(mcp_servers) if mcp_servers else 'None'}
- **Knowledge Base**: {'Enabled' if enable_knowledge_base else 'Disabled'}

### Next Steps:
To create this agent, the user should:
1. Review the configuration above
2. Use the `/create-agent` command to save it
3. Or manually save to `agents/{name}.yaml` and run `/reload-agents`

Would you like me to modify anything in this configuration?"""

    return response


def create_agent_file(
    name: str,
    yaml_content: str,
) -> str:
    """
    Create an agent file from YAML content.

    This is called after the user approves a proposed agent.

    Args:
        name: The agent name (used for filename)
        yaml_content: The YAML configuration content

    Returns:
        Success or error message
    """
    # Validate the YAML
    schema, error = validate_agent_yaml(yaml_content)
    if error:
        return f"Error: Invalid agent configuration:\n{error}"

    if schema.name != name:
        return f"Error: Name in YAML ({schema.name}) doesn't match filename ({name})"

    # Get the agents directory
    agents_dir = get_agents_directory()

    # Ensure directory exists
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Write the file
    agent_file = agents_dir / f"{name}.yaml"

    try:
        agent_file.write_text(yaml_content, encoding="utf-8")
        LOGGER.info(f"Created agent file: {agent_file}")
        return f"Successfully created agent file: {agent_file.name}"
    except Exception as e:
        LOGGER.error(f"Failed to create agent file: {e}")
        return f"Error: Failed to create agent file: {e}"


def list_available_tools() -> str:
    """
    List tools available for custom agents.

    Returns:
        Formatted list of available tools with descriptions.
    """
    tools = [
        ("universal_search", "Search the web using Brave Search API"),
        ("read_webpage", "Fetch and extract text content from web pages"),
    ]

    lines = ["## Available Tools for Custom Agents:\n"]
    for name, desc in tools:
        lines.append(f"- `{name}`: {desc}")

    lines.append("\n## MCP Servers:")
    lines.append("MCP servers must be configured in app_settings.yaml.")
    lines.append("Check your settings for available servers.")

    return "\n".join(lines)


# Create the FunctionTool instances
propose_agent_tool = FunctionTool(func=propose_agent)
list_tools_tool = FunctionTool(func=list_available_tools)

__all__ = [
    "propose_agent",
    "create_agent_file",
    "list_available_tools",
    "propose_agent_tool",
    "list_tools_tool",
]
