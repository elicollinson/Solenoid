import json
import logging
from typing import Iterable
from pathlib import Path
from google.adk.sessions import Session
from google.genai.types import Content, Part
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from google.adk.models.lite_llm import LlmRequest
import asyncio

# Use file-based logging to avoid Textual UI interference
_MEMORY_LOG_FILE = Path("memory_debug.log")
_file_handler = logging.FileHandler(_MEMORY_LOG_FILE, mode='a')
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

LOGGER = logging.getLogger("memory.extractor")
LOGGER.setLevel(logging.DEBUG)
LOGGER.addHandler(_file_handler)
LOGGER.propagate = False

# Load extraction prompt from settings (falls back to default if not found)
_DEFAULT_EXTRACTION_PROMPT = """
You are a memory extraction system. Your task is to analyze the recent conversation and extract key facts, preferences, or events that should be remembered for future interactions.

Avoid duplicating any memories that are already stored. Refer to the list of loaded memories below to prevent redundancy.

Return the output as a JSON list of objects, where each object has:
- "text": The memory content (string).
- "type": One of "profile" (user details), "episodic" (events), "semantic" (facts).
- "importance": An integer from 1 to 5 (5 being most important).

If no relevant memories are found, return an empty list [].

Loaded Stored Memories:
{existing_memories}

Recent Conversation:
{conversation_text}
"""

def get_extraction_prompt() -> str:
    """Load the memory extraction prompt from settings."""
    prompt = get_agent_prompt("memory_extractor", default=_DEFAULT_EXTRACTION_PROMPT)
    return prompt

def llm_extractor(session: Session, tail_text: str) -> Iterable[dict]:
    """Extracts memories using an LLM."""
    LOGGER.info("[Extractor] llm_extractor called")
    LOGGER.info(f"[Extractor] tail_text length: {len(tail_text)} chars")

    # We instantiate a new model client for extraction to avoid interfering with the main agent's state if any
    model = get_model("extractor")
    LOGGER.info(f"[Extractor] Got model: {model}")

    existing_memories = session.state.get("existing_memories", "None")
    LOGGER.info(f"[Extractor] Existing memories: {existing_memories}")

    extraction_prompt = get_extraction_prompt()
    prompt = extraction_prompt.format(conversation_text=tail_text, existing_memories=existing_memories)
    LOGGER.debug(f"[Extractor] Full prompt length: {len(prompt)} chars")

    try:
        from concurrent.futures import ThreadPoolExecutor

        async def _generate():
            LOGGER.info("[Extractor] Starting async generation...")
            request = LlmRequest(contents=[Content(parts=[Part.from_text(text=prompt)])])
            response_gen = model.generate_content_async(request)

            full_text = ""
            chunk_count = 0
            async for chunk in response_gen:
                chunk_count += 1
                if chunk.content and chunk.content.parts:
                    full_text += chunk.content.parts[0].text
            LOGGER.info(f"[Extractor] Received {chunk_count} chunks, total text: {len(full_text)} chars")
            return full_text

        # Since we are likely called from within an async loop (via SqliteMemoryService),
        # but this function must be synchronous, we cannot use asyncio.run() directly.
        # We run it in a separate thread to get a fresh loop.
        LOGGER.info("[Extractor] Running LLM in thread pool...")
        with ThreadPoolExecutor() as executor:
            text = executor.submit(asyncio.run, _generate()).result()

        LOGGER.info(f"[Extractor] Raw LLM response: {text[:500] if text else 'EMPTY'}...")

        # Clean up markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
            LOGGER.debug("[Extractor] Extracted from ```json block")
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            LOGGER.debug("[Extractor] Extracted from ``` block")

        text = text.strip()
        LOGGER.info(f"[Extractor] Cleaned text for parsing: {text[:300] if text else 'EMPTY'}")

        memories = json.loads(text)
        LOGGER.info(f"[Extractor] Successfully parsed JSON, got {len(memories) if isinstance(memories, list) else 'non-list'} memories")
        LOGGER.info(f"[Extractor] Memories: {memories}")
        if isinstance(memories, list):
            return memories

    except json.JSONDecodeError as e:
        LOGGER.error(f"[Extractor] JSON parse error: {e}")
        LOGGER.error(f"[Extractor] Text that failed to parse: {text[:500] if text else 'EMPTY'}")
    except Exception as e:
        LOGGER.error(f"[Extractor] Error extracting memories: {e}", exc_info=True)

    return []
