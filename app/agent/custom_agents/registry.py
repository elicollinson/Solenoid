# app/agent/custom_agents/registry.py
"""
Runtime registry for custom agents.

The registry:
- Maintains the current set of loaded custom agents
- Provides reload capability for /reload-agents command
- Tracks available tools and MCP servers for validation
- Creates ADK Agent instances from schemas
"""

import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.agent.custom_agents.schema import CustomAgentSchema
from app.agent.custom_agents.loader import load_custom_agents, AgentLoadResult

LOGGER = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """Information about an available tool."""

    name: str
    description: str
    category: str  # 'research', 'execution', 'filesystem', 'mcp'


@dataclass
class MCPServerInfo:
    """Information about an available MCP server."""

    name: str
    server_type: str  # 'stdio', 'http'
    is_available: bool


@dataclass
class RegistryState:
    """Snapshot of registry state."""

    agents: dict[str, CustomAgentSchema]
    available_tools: dict[str, ToolInfo]
    available_mcp_servers: dict[str, MCPServerInfo]
    last_reload: Optional[datetime]
    load_errors: list[str]


class CustomAgentRegistry:
    """
    Central registry for custom agents.

    This is a singleton-like class that maintains the current state of
    loaded custom agents. It provides:
    - Agent lookup by name
    - Reload capability
    - Tool/MCP server availability tracking
    - Validation of agent tool/server requests
    """

    def __init__(self):
        self._agents: dict[str, CustomAgentSchema] = {}
        self._available_tools: dict[str, ToolInfo] = {}
        self._available_mcp_servers: dict[str, MCPServerInfo] = {}
        self._last_reload: Optional[datetime] = None
        self._load_errors: list[str] = []
        self._initialized = False

    def initialize(
        self,
        available_tools: Optional[dict[str, ToolInfo]] = None,
        available_mcp_servers: Optional[dict[str, MCPServerInfo]] = None,
    ) -> AgentLoadResult:
        """
        Initialize the registry with available tools and load agents.

        Args:
            available_tools: Dictionary of available tools
            available_mcp_servers: Dictionary of available MCP servers

        Returns:
            AgentLoadResult with loaded agents and errors
        """
        if available_tools:
            self._available_tools = available_tools
        if available_mcp_servers:
            self._available_mcp_servers = available_mcp_servers

        result = self.reload()
        self._initialized = True
        return result

    def reload(self) -> AgentLoadResult:
        """
        Reload all agents from the agents/ directory.

        This is called by the /reload-agents command.

        Returns:
            AgentLoadResult with loaded agents and errors
        """
        LOGGER.info("Reloading custom agents...")

        # Load agents from files
        result = load_custom_agents()

        # Clear current state
        self._agents.clear()
        self._load_errors.clear()

        # Process loaded agents
        for agent in result.agents:
            # Validate tool availability
            unavailable_tools = self._get_unavailable_tools(agent.tools)
            if unavailable_tools:
                LOGGER.warning(
                    f"Agent '{agent.name}' requests unavailable tools: {unavailable_tools}"
                )

            # Validate MCP server availability
            unavailable_servers = self._get_unavailable_mcp_servers(agent.mcp_servers)
            if unavailable_servers:
                LOGGER.warning(
                    f"Agent '{agent.name}' requests unavailable MCP servers: {unavailable_servers}"
                )

            self._agents[agent.name] = agent
            LOGGER.info(f"Registered agent: {agent.name}")

        # Store errors
        for error in result.errors:
            self._load_errors.append(str(error))

        self._last_reload = datetime.now()

        LOGGER.info(
            f"Registry reload complete: {len(self._agents)} agents, "
            f"{len(result.errors)} errors"
        )

        return result

    def _get_unavailable_tools(self, requested_tools: list[str]) -> list[str]:
        """Get list of requested tools that are not available."""
        if not self._available_tools:
            # No tools registered yet, can't validate
            return []
        return [t for t in requested_tools if t not in self._available_tools]

    def _get_unavailable_mcp_servers(self, requested_servers: list[str]) -> list[str]:
        """Get list of requested MCP servers that are not available."""
        if not self._available_mcp_servers:
            # No servers registered yet, can't validate
            return []
        return [s for s in requested_servers if s not in self._available_mcp_servers]

    def get_agent(self, name: str) -> Optional[CustomAgentSchema]:
        """Get an agent by name."""
        return self._agents.get(name)

    def get_all_agents(self) -> list[CustomAgentSchema]:
        """Get all loaded agents."""
        return list(self._agents.values())

    def get_enabled_agents(self) -> list[CustomAgentSchema]:
        """Get all enabled agents."""
        return [a for a in self._agents.values() if a.enabled]

    def get_agent_names(self) -> list[str]:
        """Get names of all loaded agents."""
        return list(self._agents.keys())

    def has_agent(self, name: str) -> bool:
        """Check if an agent exists."""
        return name in self._agents

    def get_state(self) -> RegistryState:
        """Get a snapshot of the current registry state."""
        return RegistryState(
            agents=self._agents.copy(),
            available_tools=self._available_tools.copy(),
            available_mcp_servers=self._available_mcp_servers.copy(),
            last_reload=self._last_reload,
            load_errors=self._load_errors.copy(),
        )

    def register_tool(self, name: str, description: str, category: str) -> None:
        """Register an available tool."""
        self._available_tools[name] = ToolInfo(
            name=name,
            description=description,
            category=category,
        )

    def register_mcp_server(
        self, name: str, server_type: str, is_available: bool
    ) -> None:
        """Register an MCP server."""
        self._available_mcp_servers[name] = MCPServerInfo(
            name=name,
            server_type=server_type,
            is_available=is_available,
        )

    def get_available_tools(self) -> list[ToolInfo]:
        """Get list of all available tools."""
        return list(self._available_tools.values())

    def get_available_mcp_servers(self) -> list[MCPServerInfo]:
        """Get list of all available MCP servers."""
        return list(self._available_mcp_servers.values())

    @property
    def is_initialized(self) -> bool:
        """Check if the registry has been initialized."""
        return self._initialized

    @property
    def agent_count(self) -> int:
        """Get the number of loaded agents."""
        return len(self._agents)

    @property
    def last_reload_time(self) -> Optional[datetime]:
        """Get the time of the last reload."""
        return self._last_reload


# Global registry instance
_registry: Optional[CustomAgentRegistry] = None


def get_registry() -> CustomAgentRegistry:
    """Get the global custom agent registry (singleton)."""
    global _registry
    if _registry is None:
        _registry = CustomAgentRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
