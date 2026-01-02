# app/agent/custom_agents/tools/__init__.py
"""
Tools for agent creation and management.

This module provides FunctionTools that allow the model to:
- Create new agents via agentic workflow (plan_new_agent, execute_agent_research, create_and_populate_agent)
- Propose new custom agents (propose_agent) - legacy
- List available tools (list_available_tools)
- Research and populate knowledge bases (add_url_to_kb, add_text_to_kb)
- Search knowledge bases (search_kb)
"""

from app.agent.custom_agents.tools.propose_agent import (
    propose_agent,
    propose_agent_tool,
    create_agent_file,
    list_available_tools,
    list_tools_tool,
)

from app.agent.custom_agents.tools.research_kb import (
    add_url_to_kb,
    add_url_to_kb_tool,
    add_text_to_kb,
    add_text_to_kb_tool,
    search_kb,
    search_kb_tool,
    get_kb_stats,
    get_kb_stats_tool,
    list_agents_with_kb,
    list_agents_with_kb_tool,
)

from app.agent.custom_agents.tools.agent_creator import (
    plan_new_agent,
    plan_new_agent_tool,
    execute_agent_research,
    execute_agent_research_tool,
    create_and_populate_agent,
    create_and_populate_agent_tool,
)

__all__ = [
    # Agent creation workflow (primary)
    "plan_new_agent",
    "plan_new_agent_tool",
    "execute_agent_research",
    "execute_agent_research_tool",
    "create_and_populate_agent",
    "create_and_populate_agent_tool",
    # Agent creation (legacy)
    "propose_agent",
    "propose_agent_tool",
    "create_agent_file",
    "list_available_tools",
    "list_tools_tool",
    # KB population
    "add_url_to_kb",
    "add_url_to_kb_tool",
    "add_text_to_kb",
    "add_text_to_kb_tool",
    "search_kb",
    "search_kb_tool",
    "get_kb_stats",
    "get_kb_stats_tool",
    "list_agents_with_kb",
    "list_agents_with_kb_tool",
]
