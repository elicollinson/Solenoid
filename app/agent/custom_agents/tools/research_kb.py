# app/agent/custom_agents/tools/research_kb.py
"""
Tools for researching and populating agent knowledge bases.

These tools allow the model to:
- Search for relevant content on a topic
- Propose sources for the user to approve
- Ingest approved content into an agent's KB
"""

import logging
from typing import Optional

from google.adk.tools import FunctionTool

from app.agent.custom_agents.registry import get_registry
from app.agent.knowledge_base import (
    get_kb_manager,
    ingest_url,
    ingest_text,
    search_agent_kb,
)

LOGGER = logging.getLogger(__name__)


def add_url_to_kb(
    agent_name: str,
    url: str,
) -> str:
    """
    Add content from a URL to an agent's knowledge base.

    Fetches the URL, extracts text content, chunks it, and stores
    with embeddings for later retrieval.

    Args:
        agent_name: Name of the custom agent whose KB to populate.
                    Must be an existing custom agent with KB enabled.
        url: The URL to fetch and ingest.
             Should be a publicly accessible web page.

    Returns:
        Result message indicating success or failure with details.
    """
    # Validate agent exists
    registry = get_registry()
    if not registry.has_agent(agent_name):
        return f"Error: No custom agent named '{agent_name}' exists."

    agent_schema = registry.get_agent(agent_name)
    if not agent_schema.knowledge_base.enabled:
        return f"Error: Agent '{agent_name}' does not have knowledge base enabled."

    try:
        result = ingest_url(agent_name, url)

        if result.success:
            return (
                f"Successfully added content to {agent_name}'s knowledge base:\n"
                f"- Source: {result.title or url}\n"
                f"- Chunks created: {result.chunk_count}\n"
                f"- Total characters: {result.total_chars}\n"
                f"- Document ID: {result.doc_id}"
            )
        else:
            return f"Error ingesting URL: {result.error}"

    except Exception as e:
        LOGGER.error(f"Failed to add URL to KB: {e}")
        return f"Error: Failed to add URL to knowledge base: {e}"


def add_text_to_kb(
    agent_name: str,
    text: str,
    title: Optional[str] = None,
) -> str:
    """
    Add text content directly to an agent's knowledge base.

    Chunks the text and stores with embeddings for later retrieval.
    Useful for adding notes, documentation, or processed content.

    Args:
        agent_name: Name of the custom agent whose KB to populate.
        text: The text content to add. Will be chunked automatically.
        title: Optional title/label for this content.

    Returns:
        Result message indicating success or failure.
    """
    # Validate agent exists
    registry = get_registry()
    if not registry.has_agent(agent_name):
        return f"Error: No custom agent named '{agent_name}' exists."

    agent_schema = registry.get_agent(agent_name)
    if not agent_schema.knowledge_base.enabled:
        return f"Error: Agent '{agent_name}' does not have knowledge base enabled."

    if not text.strip():
        return "Error: Text content is empty."

    try:
        result = ingest_text(agent_name, text, title=title)

        if result.success:
            return (
                f"Successfully added content to {agent_name}'s knowledge base:\n"
                f"- Title: {result.title or '(untitled)'}\n"
                f"- Chunks created: {result.chunk_count}\n"
                f"- Total characters: {result.total_chars}"
            )
        else:
            return f"Error ingesting text: {result.error}"

    except Exception as e:
        LOGGER.error(f"Failed to add text to KB: {e}")
        return f"Error: Failed to add text to knowledge base: {e}"


def search_kb(
    agent_name: str,
    query: str,
    top_k: int = 5,
) -> str:
    """
    Search an agent's knowledge base.

    Uses hybrid search (vector + keyword) with reranking
    to find the most relevant content.

    Args:
        agent_name: Name of the custom agent whose KB to search.
        query: The search query.
        top_k: Number of results to return (1-20).

    Returns:
        Formatted search results or error message.
    """
    # Validate agent exists
    registry = get_registry()
    if not registry.has_agent(agent_name):
        return f"Error: No custom agent named '{agent_name}' exists."

    agent_schema = registry.get_agent(agent_name)
    if not agent_schema.knowledge_base.enabled:
        return f"Error: Agent '{agent_name}' does not have knowledge base enabled."

    top_k = max(1, min(20, top_k))

    try:
        results = search_agent_kb(
            agent_name=agent_name,
            query_text=query,
            top_n=top_k,
        )

        if not results:
            return f"No results found in {agent_name}'s knowledge base for: {query}"

        lines = [f"## Search Results for '{query}' in {agent_name}'s KB:\n"]

        for i, (text, score, chunk) in enumerate(results, 1):
            source = ""
            if chunk.title:
                source = f" (from: {chunk.title})"
            elif chunk.url:
                source = f" (from: {chunk.url})"

            # Truncate text for display
            display_text = text[:500] + "..." if len(text) > 500 else text

            lines.append(f"### [{i}] Score: {score:.3f}{source}")
            lines.append(display_text)
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        LOGGER.error(f"KB search failed: {e}")
        return f"Error: Search failed: {e}"


def get_kb_stats(agent_name: str) -> str:
    """
    Get statistics about an agent's knowledge base.

    Args:
        agent_name: Name of the custom agent.

    Returns:
        Formatted statistics or error message.
    """
    registry = get_registry()
    if not registry.has_agent(agent_name):
        return f"Error: No custom agent named '{agent_name}' exists."

    try:
        manager = get_kb_manager()
        stats = manager.get_stats(agent_name)

        return (
            f"## Knowledge Base Statistics for {agent_name}:\n"
            f"- Total chunks: {stats.chunk_count}\n"
            f"- Unique documents: {stats.doc_count}\n"
            f"- Total text length: {stats.total_text_length:,} characters\n"
            f"- Embeddings stored: {stats.embedding_count}\n"
            f"- Embeddings available: {'Yes' if stats.has_embeddings else 'No'}"
        )

    except Exception as e:
        LOGGER.error(f"Failed to get KB stats: {e}")
        return f"Error: Failed to get statistics: {e}"


def list_agents_with_kb() -> str:
    """
    List all custom agents that have knowledge bases enabled.

    Returns:
        Formatted list of agents with KB status.
    """
    registry = get_registry()

    if not registry.is_initialized:
        return "No custom agents loaded. Use /reload-agents to load agents."

    agents = registry.get_all_agents()

    if not agents:
        return "No custom agents defined. Create one with the propose_agent tool."

    lines = ["## Custom Agents with Knowledge Bases:\n"]

    kb_enabled = []
    kb_disabled = []

    for agent in agents:
        if agent.knowledge_base.enabled:
            kb_enabled.append(agent)
        else:
            kb_disabled.append(agent)

    if kb_enabled:
        lines.append("### KB Enabled:")
        for agent in kb_enabled:
            manager = get_kb_manager()
            try:
                stats = manager.get_stats(agent.name)
                lines.append(
                    f"- `{agent.name}`: {stats.chunk_count} chunks, "
                    f"{stats.doc_count} documents"
                )
            except Exception:
                lines.append(f"- `{agent.name}`: (stats unavailable)")

    if kb_disabled:
        lines.append("\n### KB Disabled:")
        for agent in kb_disabled:
            lines.append(f"- `{agent.name}`")

    return "\n".join(lines)


# Create FunctionTool instances
add_url_to_kb_tool = FunctionTool(func=add_url_to_kb)
add_text_to_kb_tool = FunctionTool(func=add_text_to_kb)
search_kb_tool = FunctionTool(func=search_kb)
get_kb_stats_tool = FunctionTool(func=get_kb_stats)
list_agents_with_kb_tool = FunctionTool(func=list_agents_with_kb)

__all__ = [
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
