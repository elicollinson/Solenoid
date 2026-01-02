# app/agent/callbacks/memory.py
"""
Memory callbacks for the agent system.

This module provides callbacks for:
1. Injecting relevant memories into prompts (before_model_callback)
2. Extracting and storing memories from final responses (after_model_callback)

Architecture:
- inject_memories: Runs on user_proxy_agent only (entry point)
- save_memories_on_final_response: Runs on ALL agents that produce output

Final Response Detection (per Google ADK docs):
A response is considered "final" (user-facing) when:
- It contains text content (not empty)
- It does NOT contain a function_call (not delegating to tool/agent)
- It is NOT partial (streaming complete)
"""

import asyncio
import logging
from typing import Optional
from pathlib import Path

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from app.agent.config import get_embedding_config
from app.agent.memory.adk_sqlite_memory import SqliteMemoryService
from app.agent.memory.search import search_memories
from app.agent.memory.extractor import llm_extractor

# Set up file-based logging for memory debugging
# This avoids interfering with the Textual UI
_MEMORY_LOG_FILE = Path("memory_debug.log")
_file_handler = logging.FileHandler(_MEMORY_LOG_FILE, mode='a')
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(_file_handler)
# Also log to a dedicated memory logger that writes to file
LOGGER.propagate = False  # Don't propagate to root (avoids stdout interference)

# Session state keys for memory management
_MEMORY_EXTRACTED_KEY = "_memory_extracted_for_invocation"

# Singleton memory service instance
_memory_service: Optional[SqliteMemoryService] = None


def get_memory_service() -> SqliteMemoryService:
    """Get or create the singleton memory service instance."""
    global _memory_service
    if _memory_service is None:
        # Load embedding config from settings
        embed_config = get_embedding_config()
        LOGGER.info(f"[Memory] Initializing memory service with embedding config: {embed_config}")

        _memory_service = SqliteMemoryService(
            db_path="memories.db",
            ollama_host=embed_config["host"],
            embedding_model=embed_config["model"],
            extractor=llm_extractor
        )
    return _memory_service


def inject_memories(callback_context: CallbackContext, llm_request) -> None:
    """
    Before model callback: Search and inject relevant memories into the prompt.

    This should ONLY be used on the entry-point agent (user_proxy_agent)
    to inject memories once at the start of processing.

    Args:
        callback_context: The callback context with session info
        llm_request: The LLM request to potentially modify
    """
    try:
        # Extract user text from the request
        user_text = _extract_text_from_request(llm_request)
        if not user_text:
            return

        # Access session - prefer invocation_context for consistency
        invocation_context = getattr(callback_context, '_invocation_context', None)
        if invocation_context:
            session = getattr(invocation_context, 'session', callback_context.session)
        else:
            session = callback_context.session

        memory_service = get_memory_service()

        # Search for relevant memories
        hits = search_memories(
            memory_service.conn,
            query_text=user_text,
            user_id=session.user_id,
            app_name=session.app_name,
            top_n=5
        )

        if not hits:
            return

        # Format memories for injection
        memory_text = "\n".join([f"- {text}" for text, score, row in hits])

        # Store for extractor use (to avoid duplicating memories)
        session.state["existing_memories"] = memory_text

        # Inject into the llm_request as additional context
        injection = f"\n\nRelevant Memories:\n{memory_text}"
        if llm_request.contents:
            llm_request.contents[-1].parts.append(types.Part.from_text(text=injection))

        LOGGER.info(f"[Memory] Injected {len(hits)} memories into prompt")
        for i, (text, score, row) in enumerate(hits, 1):
            LOGGER.debug(f"  [{i}] (score={score:.2f}): {text}")

    except Exception as e:
        LOGGER.error(f"[Memory] Failed to inject memories: {e}")


async def save_memories_on_final_response(callback_context: CallbackContext, llm_response) -> None:
    """
    After model callback: Extract and save memories when a final response is detected.

    A "final response" is one that:
    1. Contains text content (user-facing output)
    2. Does NOT contain a function_call (not delegating to tool/agent)
    3. Is NOT partial (streaming is complete)

    This callback should be added to ALL agents that may produce final output.
    It uses session state to ensure memory extraction only happens once per interaction.

    NOTE: This is an async callback - ADK supports both sync and async callbacks.
    We await the memory extraction to ensure it completes before the response is finalized.

    Args:
        callback_context: The callback context with session info
        llm_response: The LLM response to check
    """
    try:
        agent_name = callback_context.agent_name
        invocation_id = callback_context.invocation_id

        LOGGER.info(f"[Memory] after_model_callback triggered for {agent_name} (invocation: {invocation_id})")

        # Check if we've already extracted memories for this invocation
        extracted_key = f"{_MEMORY_EXTRACTED_KEY}:{invocation_id}"
        if callback_context.session.state.get(extracted_key):
            LOGGER.info(f"[Memory] Already extracted for invocation {invocation_id}, skipping")
            return

        # Check if this is a final response
        if not _is_final_response(llm_response):
            LOGGER.info(f"[Memory] Response from {agent_name} is not final (tool call or partial), skipping")
            return

        # Mark as extracted to prevent duplicates
        callback_context.session.state[extracted_key] = True

        LOGGER.info(f"[Memory] *** Final response detected from {agent_name}, starting extraction... ***")

        # Await memory extraction to ensure it completes before response is finalized
        memory_service = get_memory_service()

        # Per ADK docs, access session via _invocation_context for full event history
        # callback_context.session may not have events populated
        invocation_context = getattr(callback_context, '_invocation_context', None)
        if invocation_context:
            session = getattr(invocation_context, 'session', callback_context.session)
            LOGGER.info(f"[Memory] Using session from invocation_context (events: {len(getattr(session, 'events', []))})")
        else:
            session = callback_context.session
            LOGGER.info(f"[Memory] Using session from callback_context (events: {len(getattr(session, 'events', []))})")

        await memory_service.add_session_to_memory(session)
        LOGGER.info("[Memory] *** Memory extraction completed ***")

    except Exception as e:
        LOGGER.error(f"[Memory] Failed to save memories: {e}", exc_info=True)


def _extract_text_from_request(llm_request) -> str:
    """Extract text content from an LLM request."""
    user_text = ""
    if llm_request.contents:
        for content in llm_request.contents:
            if content.parts:
                for part in content.parts:
                    if hasattr(part, 'text') and part.text:
                        user_text += part.text + "\n"
    return user_text.strip()


def _is_final_response(llm_response) -> bool:
    """
    Determine if an LLM response is a "final" user-facing response.

    Per Google ADK documentation, a final response:
    1. Is NOT partial (streaming complete)
    2. Contains NO function_call (not delegating to tool/agent)
    3. Contains text content (has something to show user)

    Args:
        llm_response: The LLM response to check

    Returns:
        True if this is a final response, False otherwise
    """
    if llm_response is None:
        LOGGER.debug("[Memory] _is_final_response: llm_response is None")
        return False

    # Check if response is partial (streaming chunk)
    # ADK uses 'partial' attribute on the response or event
    is_partial = getattr(llm_response, 'partial', False)
    if is_partial:
        LOGGER.debug("[Memory] _is_final_response: response is partial")
        return False

    # Check content exists
    content = getattr(llm_response, 'content', None)
    if content is None:
        LOGGER.debug("[Memory] _is_final_response: content is None")
        return False

    parts = getattr(content, 'parts', None)
    if not parts:
        LOGGER.debug("[Memory] _is_final_response: no parts in content")
        return False

    # Check each part - if ANY part has a function_call, this is not final
    has_text = False
    has_function_call = False

    for part in parts:
        # Check for function_call (tool/agent delegation)
        if hasattr(part, 'function_call') and part.function_call:
            has_function_call = True
            func_name = getattr(part.function_call, 'name', 'unknown')
            LOGGER.debug(f"[Memory] _is_final_response: found function_call: {func_name}")
            break

        # Check for text content
        if hasattr(part, 'text') and part.text:
            has_text = True
            text_preview = part.text[:50] + "..." if len(part.text) > 50 else part.text
            LOGGER.debug(f"[Memory] _is_final_response: found text: {text_preview}")

    # Final response: has text, no function calls
    if has_function_call:
        LOGGER.debug("[Memory] _is_final_response: NOT final (has function_call)")
        return False

    if not has_text:
        LOGGER.debug("[Memory] _is_final_response: NOT final (no text content)")
        return False

    LOGGER.info("[Memory] _is_final_response: IS FINAL (has text, no function_call)")
    return True
