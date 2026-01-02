# app/agent/custom_agents/factory.py
"""
Factory for creating ADK Agent instances from CustomAgentSchema.

This module bridges the gap between the YAML schema and runtime ADK agents,
handling:
- Model resolution (agent-specific or default)
- Tool filtering based on agent's allowed tools
- MCP server filtering
- Knowledge base injection callback setup
"""

import logging
from typing import Optional, Any
from google.adk.agents import Agent
from google.adk.tools import FunctionTool

from app.agent.custom_agents.schema import CustomAgentSchema
from app.agent.models.factory import get_model
from app.agent.callbacks.memory import save_memories_on_final_response
from app.agent.knowledge_base.callbacks import get_kb_callback_for_agent
from app.agent.knowledge_base.manager import get_kb_manager

LOGGER = logging.getLogger(__name__)


class AgentFactory:
    """
    Factory for creating ADK Agent instances from custom agent schemas.

    The factory is initialized with the available tools and MCP toolsets,
    then can create Agent instances that only have access to their
    allowed tools.
    """

    def __init__(self):
        # Tool name -> FunctionTool instance
        self._tools: dict[str, FunctionTool] = {}
        # MCP server name -> list of tools from that server
        self._mcp_tools: dict[str, list[Any]] = {}
        # Callback for KB injection (set when KB system is ready)
        self._kb_injection_callback: Optional[Any] = None

    def register_tool(self, name: str, tool: FunctionTool) -> None:
        """Register a tool that can be assigned to agents."""
        self._tools[name] = tool
        LOGGER.debug(f"Registered tool: {name}")

    def register_mcp_tools(self, server_name: str, tools: list[Any]) -> None:
        """Register tools from an MCP server."""
        self._mcp_tools[server_name] = tools
        LOGGER.debug(f"Registered MCP server: {server_name} with {len(tools)} tools")

    def set_kb_injection_callback(self, callback: Any) -> None:
        """Set the callback for knowledge base injection."""
        self._kb_injection_callback = callback

    def create_agent(self, schema: CustomAgentSchema) -> Agent:
        """
        Create an ADK Agent instance from a CustomAgentSchema.

        Args:
            schema: The agent schema from YAML

        Returns:
            Configured ADK Agent instance
        """
        LOGGER.info(f"Creating agent: {schema.name}")

        # Resolve model
        model = self._resolve_model(schema)

        # Collect allowed tools
        tools = self._collect_tools(schema)

        # Build callbacks
        callbacks = self._build_callbacks(schema)

        # Create the agent
        agent = Agent(
            name=schema.name,
            model=model,
            description=schema.description,
            instruction=schema.instruction,
            tools=tools if tools else None,
            after_model_callback=callbacks.get("after_model_callback"),
            before_model_callback=callbacks.get("before_model_callback"),
        )

        LOGGER.info(
            f"Created agent '{schema.name}' with {len(tools)} tools"
        )

        return agent

    def _resolve_model(self, schema: CustomAgentSchema) -> Any:
        """
        Resolve the model for an agent.

        Priority:
        1. Agent-specific model config in schema
        2. Default 'agent' model from settings
        """
        if schema.model:
            # Use agent-specific model
            model_name = schema.model.name
            provider = schema.model.provider
            LOGGER.debug(
                f"Agent '{schema.name}' using custom model: {model_name} ({provider})"
            )
        # Use the model factory - it will check for agent-specific config first,
        # then fall back to generic agent config
        return get_model(schema.name)

    def _collect_tools(self, schema: CustomAgentSchema) -> list[Any]:
        """
        Collect the tools this agent is allowed to use.

        Combines:
        - Explicitly listed tools
        - Tools from allowed MCP servers
        """
        tools: list[Any] = []

        # Add explicitly listed tools
        for tool_name in schema.tools:
            if tool_name in self._tools:
                tools.append(self._tools[tool_name])
                LOGGER.debug(f"Agent '{schema.name}' granted tool: {tool_name}")
            else:
                LOGGER.warning(
                    f"Agent '{schema.name}' requests unknown tool: {tool_name}"
                )

        # Add MCP server tools
        for server_name in schema.mcp_servers:
            if server_name in self._mcp_tools:
                server_tools = self._mcp_tools[server_name]
                tools.extend(server_tools)
                LOGGER.debug(
                    f"Agent '{schema.name}' granted {len(server_tools)} tools "
                    f"from MCP server: {server_name}"
                )
            else:
                LOGGER.warning(
                    f"Agent '{schema.name}' requests unknown MCP server: {server_name}"
                )

        return tools

    def _build_callbacks(self, schema: CustomAgentSchema) -> dict[str, list[Any]]:
        """
        Build the callback lists for an agent.

        Includes:
        - Memory saving callback (standard for all agents)
        - KB injection callback (if KB is enabled)
        """
        callbacks: dict[str, list[Any]] = {
            "after_model_callback": [],
            "before_model_callback": [],
        }

        # Standard memory callback
        callbacks["after_model_callback"].append(save_memories_on_final_response)

        # KB injection callback (if enabled)
        if schema.knowledge_base.enabled:
            kb_callback = get_kb_callback_for_agent(schema)
            if kb_callback:
                callbacks["before_model_callback"].append(kb_callback)
                LOGGER.debug(f"Added KB injection callback for {schema.name}")

            # Ensure KB tables exist
            try:
                kb_manager = get_kb_manager()
                kb_manager.ensure_kb_exists(schema.name)
            except Exception as e:
                LOGGER.warning(f"Failed to ensure KB for {schema.name}: {e}")

        return callbacks

    def create_all_agents(
        self, schemas: list[CustomAgentSchema]
    ) -> dict[str, Agent]:
        """
        Create Agent instances for all provided schemas.

        Args:
            schemas: List of agent schemas to create

        Returns:
            Dictionary mapping agent names to Agent instances
        """
        agents: dict[str, Agent] = {}

        for schema in schemas:
            if not schema.enabled:
                LOGGER.info(f"Skipping disabled agent: {schema.name}")
                continue

            try:
                agent = self.create_agent(schema)
                agents[schema.name] = agent
            except Exception as e:
                LOGGER.error(f"Failed to create agent '{schema.name}': {e}")

        return agents


# Global factory instance
_factory: Optional[AgentFactory] = None


def get_factory() -> AgentFactory:
    """Get the global agent factory (singleton)."""
    global _factory
    if _factory is None:
        _factory = AgentFactory()
    return _factory


def reset_factory() -> None:
    """Reset the global factory (for testing)."""
    global _factory
    _factory = None
