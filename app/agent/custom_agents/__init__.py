# app/agent/custom_agents/__init__.py
"""
Dynamic custom agent system.

This module provides the ability to define, load, and manage custom agents
via YAML configuration files in the `agents/` directory.
"""

from app.agent.custom_agents.schema import (
    CustomAgentSchema,
    AgentModelConfig,
    AgentKBConfig,
    AgentMetadata,
)
from app.agent.custom_agents.loader import (
    load_custom_agents,
    load_agent_from_file,
    get_agents_directory,
    validate_agent_yaml,
)
from app.agent.custom_agents.registry import (
    CustomAgentRegistry,
    get_registry,
    ToolInfo,
    MCPServerInfo,
)
from app.agent.custom_agents.factory import (
    AgentFactory,
    get_factory,
)

__all__ = [
    # Schema
    "CustomAgentSchema",
    "AgentModelConfig",
    "AgentKBConfig",
    "AgentMetadata",
    # Loader
    "load_custom_agents",
    "load_agent_from_file",
    "get_agents_directory",
    "validate_agent_yaml",
    # Registry
    "CustomAgentRegistry",
    "get_registry",
    "ToolInfo",
    "MCPServerInfo",
    # Factory
    "AgentFactory",
    "get_factory",
]
