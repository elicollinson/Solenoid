# app/agent/custom_agents/setup.py
"""
Setup and initialization for the custom agent system.

This module provides the entry point for initializing:
- Tool registry with available tools
- MCP server registry
- Custom agent loading and factory
- Planning agent integration
"""

import logging
from typing import Any, Optional
from google.adk.agents import Agent

from app.agent.custom_agents.registry import get_registry, ToolInfo, MCPServerInfo
from app.agent.custom_agents.factory import get_factory
from app.agent.custom_agents.loader import load_custom_agents
from app.agent.config import load_settings

LOGGER = logging.getLogger(__name__)


def register_builtin_tools(factory) -> None:
    """
    Register the built-in tools that custom agents can use.

    These are the same tools used by the static agents.
    """
    from app.agent.search.universal_search import create_universal_search_tool
    from app.agent.search.web_retrieval import read_webpage_tool

    # Register search tools
    search_tool = create_universal_search_tool()
    factory.register_tool("universal_search", search_tool)
    get_registry().register_tool(
        "universal_search",
        "Search the web using Brave Search",
        "research"
    )

    factory.register_tool("read_webpage", read_webpage_tool)
    get_registry().register_tool(
        "read_webpage",
        "Fetch and read content from a web page",
        "research"
    )

    LOGGER.info("Registered 2 built-in tools")


def register_mcp_servers() -> None:
    """
    Register available MCP servers from settings.

    This reads the mcp_servers section from app_settings.yaml and
    registers them so custom agents can request access.
    """
    settings = load_settings()
    mcp_config = settings.get("mcp_servers", {})

    registry = get_registry()

    for server_name, server_config in mcp_config.items():
        server_type = server_config.get("type", "stdio")
        # Assume available if configured (actual availability checked at runtime)
        registry.register_mcp_server(server_name, server_type, is_available=True)

    LOGGER.info(f"Registered {len(mcp_config)} MCP servers")


def load_mcp_tools_for_agent(
    agent_schema,
    mcp_toolsets: Optional[dict[str, Any]] = None
) -> list[Any]:
    """
    Load MCP tools for a specific agent based on its allowed servers.

    Args:
        agent_schema: The agent schema with mcp_servers list
        mcp_toolsets: Dictionary of server_name -> toolset from MCP loading

    Returns:
        List of tools from allowed MCP servers
    """
    if not mcp_toolsets:
        return []

    tools = []
    for server_name in agent_schema.mcp_servers:
        if server_name in mcp_toolsets:
            toolset = mcp_toolsets[server_name]
            # MCP toolsets may be a list or single toolset
            if isinstance(toolset, list):
                tools.extend(toolset)
            else:
                tools.append(toolset)
            LOGGER.debug(f"Loaded MCP tools from {server_name} for agent {agent_schema.name}")

    return tools


def initialize_custom_agents(
    mcp_toolsets: Optional[dict[str, Any]] = None
) -> list[Agent]:
    """
    Initialize the custom agent system and create agent instances.

    This is the main entry point for setting up custom agents.
    Should be called during server startup.

    Args:
        mcp_toolsets: Optional dictionary of loaded MCP toolsets

    Returns:
        List of ADK Agent instances for custom agents
    """
    LOGGER.info("Initializing custom agent system...")

    factory = get_factory()
    registry = get_registry()

    # Register built-in tools
    register_builtin_tools(factory)

    # Register MCP servers
    register_mcp_servers()

    # If MCP toolsets provided, register them with factory
    if mcp_toolsets:
        for server_name, toolset in mcp_toolsets.items():
            tools = toolset if isinstance(toolset, list) else [toolset]
            factory.register_mcp_tools(server_name, tools)

    # Initialize registry (loads agents from files)
    result = registry.initialize()

    if result.errors:
        for error in result.errors:
            LOGGER.error(f"Agent load error: {error}")

    # Create ADK Agent instances
    agents = factory.create_all_agents(result.agents)

    LOGGER.info(
        f"Custom agent system initialized: {len(agents)} agents created, "
        f"{result.failed_count} errors"
    )

    return list(agents.values())


def reload_custom_agents(
    mcp_toolsets: Optional[dict[str, Any]] = None
) -> tuple[list[Agent], list[str]]:
    """
    Reload custom agents from the agents/ directory.

    This is called by the /reload-agents command.

    Args:
        mcp_toolsets: Optional dictionary of loaded MCP toolsets

    Returns:
        Tuple of (list of new Agent instances, list of error messages)
    """
    LOGGER.info("Reloading custom agents...")

    factory = get_factory()
    registry = get_registry()

    # Reload registry (re-scans files)
    result = registry.reload()

    # If MCP toolsets provided, update factory
    if mcp_toolsets:
        for server_name, toolset in mcp_toolsets.items():
            tools = toolset if isinstance(toolset, list) else [toolset]
            factory.register_mcp_tools(server_name, tools)

    # Create new ADK Agent instances
    agents = factory.create_all_agents(result.agents)

    errors = [str(e) for e in result.errors]

    LOGGER.info(f"Reload complete: {len(agents)} agents, {len(errors)} errors")

    return list(agents.values()), errors


def get_custom_agent_list() -> list[dict]:
    """
    Get information about all loaded custom agents.

    Returns:
        List of agent info dictionaries
    """
    registry = get_registry()

    agents_info = []
    for agent in registry.get_all_agents():
        agents_info.append({
            "name": agent.name,
            "description": agent.description,
            "enabled": agent.enabled,
            "tools": agent.tools,
            "mcp_servers": agent.mcp_servers,
            "has_kb": agent.knowledge_base.enabled,
        })

    return agents_info
