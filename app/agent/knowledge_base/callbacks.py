# app/agent/knowledge_base/callbacks.py
"""
ADK callbacks for knowledge base integration.

Provides before_model_callback that injects relevant KB content
into the agent's context before each model call.
"""

import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.genai.types import Content, Part

from app.agent.knowledge_base.search import search_agent_kb, format_kb_context

LOGGER = logging.getLogger(__name__)

# Session state key for tracking KB injection
_KB_INJECTED_KEY = "_kb_injected_for_turn"


def create_kb_injection_callback(
    agent_name: str,
    top_k: int = 10,
    min_score: float = 0.3,
    max_context_length: int = 4000,
):
    """
    Create a before_model_callback that injects KB content.

    Args:
        agent_name: The agent's name (for KB lookup)
        top_k: Number of top results to include
        min_score: Minimum reranker score to include
        max_context_length: Maximum length of injected context

    Returns:
        Callback function for use with ADK agents
    """

    def inject_kb_context(callback_context: CallbackContext) -> Optional[Content]:
        """
        Before-model callback that searches the agent's KB and injects
        relevant content into the model request.
        """
        try:
            # Get the LLM request
            llm_request = callback_context.llm_request
            if not llm_request or not llm_request.contents:
                return None

            # Check if we've already injected for this turn
            session = callback_context.session
            if session:
                turn_id = len(llm_request.contents)
                injected_for = session.state.get(_KB_INJECTED_KEY, -1)
                if injected_for == turn_id:
                    return None
                session.state[_KB_INJECTED_KEY] = turn_id

            # Extract query from the most recent user message
            query = None
            for content in reversed(llm_request.contents):
                if content.role == "user" and content.parts:
                    for part in content.parts:
                        if hasattr(part, "text") and part.text:
                            query = part.text
                            break
                    if query:
                        break

            if not query:
                LOGGER.debug(f"No query found for KB injection ({agent_name})")
                return None

            # Search the agent's KB
            results = search_agent_kb(
                agent_name=agent_name,
                query_text=query,
                top_n=top_k,
                min_score=min_score,
            )

            if not results:
                LOGGER.debug(f"No KB results for query in {agent_name}")
                return None

            # Format results as context
            kb_context = format_kb_context(results, max_length=max_context_length)

            if not kb_context:
                return None

            LOGGER.info(
                f"Injecting {len(results)} KB chunks for {agent_name} "
                f"({len(kb_context)} chars)"
            )

            # Inject as a system-like context at the start
            # We prepend to the first user message content
            if llm_request.contents:
                first_content = llm_request.contents[0]
                if first_content.parts:
                    # Create new parts list with KB context prepended
                    kb_part = Part(text=f"\n{kb_context}\n---\n")
                    new_parts = [kb_part] + list(first_content.parts)
                    first_content.parts = new_parts

            return None  # Don't short-circuit, continue with modified request

        except Exception as e:
            LOGGER.error(f"KB injection failed for {agent_name}: {e}")
            return None

    return inject_kb_context


def get_kb_callback_for_agent(agent_schema) -> Optional[callable]:
    """
    Get a KB injection callback for a custom agent schema.

    Args:
        agent_schema: CustomAgentSchema with KB configuration

    Returns:
        Callback function if KB is enabled, None otherwise
    """
    if not agent_schema.knowledge_base.enabled:
        return None

    return create_kb_injection_callback(
        agent_name=agent_schema.name,
        top_k=agent_schema.knowledge_base.search_top_k,
        min_score=agent_schema.knowledge_base.search_threshold,
    )


__all__ = [
    "create_kb_injection_callback",
    "get_kb_callback_for_agent",
]
