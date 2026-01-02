# app/agent/custom_agents/schema.py
"""
Pydantic schemas for custom agent YAML configuration.

These schemas define the structure of agent YAML files and provide
validation to catch errors early.
"""

import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# Valid agent name pattern: lowercase letters, numbers, underscores
# Must start with a letter, used for table names and identifiers
AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class AgentModelConfig(BaseModel):
    """Model configuration for a custom agent."""

    name: str = Field(..., description="Model name (e.g., 'gpt-oss:20b')")
    provider: str = Field(
        default="ollama_chat",
        description="Model provider (ollama_chat, openai, anthropic, litellm)",
    )

    class Config:
        extra = "allow"  # Allow additional model-specific config


class AgentKBConfig(BaseModel):
    """Knowledge base configuration for a custom agent."""

    enabled: bool = Field(default=True, description="Whether KB is enabled for this agent")
    search_top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of top results to retrieve from KB search",
    )
    search_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold for KB search results",
    )


class AgentMetadata(BaseModel):
    """Metadata about the agent (non-functional, for organization)."""

    author: str = Field(default="user", description="Who created this agent")
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When the agent was created",
    )
    version: int = Field(default=1, ge=1, description="Agent version number")
    tags: list[str] = Field(default_factory=list, description="Tags for organization")


class CustomAgentSchema(BaseModel):
    """
    Complete schema for a custom agent YAML file.

    Example YAML:
        name: legal_research_agent
        description: "Specializes in legal document analysis"
        instruction: |
          You are an expert legal researcher...
        model:
          name: gpt-oss:20b
          provider: ollama_chat
        tools:
          - universal_search
          - read_webpage
        mcp_servers:
          - filesystem
        knowledge_base:
          enabled: true
          search_top_k: 10
        metadata:
          author: user
          tags: [legal, research]
        enabled: true
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Agent identifier (lowercase, underscores allowed)",
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Brief description of what the agent does",
    )
    instruction: str = Field(
        ...,
        min_length=20,
        description="System prompt / instruction for the agent",
    )

    # Optional model override (uses default if not specified)
    model: Optional[AgentModelConfig] = Field(
        default=None,
        description="Optional model configuration override",
    )

    # Tool access (explicit selection)
    tools: list[str] = Field(
        default_factory=list,
        description="List of tool names this agent can use",
    )

    # MCP server access (explicit selection)
    mcp_servers: list[str] = Field(
        default_factory=list,
        description="List of MCP server names this agent can access",
    )

    # Knowledge base configuration
    knowledge_base: AgentKBConfig = Field(
        default_factory=AgentKBConfig,
        description="Knowledge base settings",
    )

    # Metadata (optional, for organization)
    metadata: AgentMetadata = Field(
        default_factory=AgentMetadata,
        description="Agent metadata",
    )

    # Enable/disable without deleting
    enabled: bool = Field(
        default=True,
        description="Whether this agent is active",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate agent name is a valid identifier for SQL table names."""
        if not AGENT_NAME_PATTERN.match(v):
            raise ValueError(
                f"Agent name must start with a lowercase letter and contain only "
                f"lowercase letters, numbers, and underscores. Got: '{v}'"
            )
        # Reserved names that could conflict with system agents
        reserved = {
            "user_proxy_agent",
            "prime_agent",
            "planning_agent",
            "code_executor_agent",
            "chart_generator_agent",
            "research_agent",
            "generic_executor_agent",
            "mcp_agent",
        }
        if v in reserved:
            raise ValueError(f"Agent name '{v}' is reserved for system agents")
        return v

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, v: list[str]) -> list[str]:
        """Validate tool names are non-empty and unique."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate tool names are not allowed")
        for tool in v:
            if not tool or not tool.strip():
                raise ValueError("Tool names cannot be empty")
        return v

    @field_validator("mcp_servers")
    @classmethod
    def validate_mcp_servers(cls, v: list[str]) -> list[str]:
        """Validate MCP server names are non-empty and unique."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate MCP server names are not allowed")
        for server in v:
            if not server or not server.strip():
                raise ValueError("MCP server names cannot be empty")
        return v

    class Config:
        extra = "forbid"  # Catch typos in YAML keys
