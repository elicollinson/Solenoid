import json
import logging
from typing import Iterable
from google.adk.sessions import Session
from google.genai.types import Content, Part
from app.agent.models.granite import get_granite_model
from google.adk.models.lite_llm import LlmRequest
import asyncio

LOGGER = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are a memory extraction system. Your task is to analyze the recent conversation and extract key facts, preferences, or events that should be remembered for future interactions.

Return the output as a JSON list of objects, where each object has:
- "text": The memory content (string).
- "type": One of "profile" (user details), "episodic" (events), "semantic" (facts).
- "importance": An integer from 1 to 5 (5 being most important).

If no relevant memories are found, return an empty list [].

Recent Conversation:
{conversation_text}
"""

def llm_extractor(session: Session, tail_text: str) -> Iterable[dict]:
    """Extracts memories using an LLM."""
    # We instantiate a new model client for extraction to avoid interfering with the main agent's state if any
    model = get_granite_model()
    
    prompt = EXTRACTION_PROMPT.format(conversation_text=tail_text)
    
    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        async def _generate():
            request = LlmRequest(contents=[Content(parts=[Part.from_text(text=prompt)])])
            response_gen = model.generate_content_async(request)
            
            full_text = ""
            async for chunk in response_gen:
                if chunk.content and chunk.content.parts:
                    full_text += chunk.content.parts[0].text
            return full_text

        # Since we are likely called from within an async loop (via SqliteMemoryService),
        # but this function must be synchronous, we cannot use asyncio.run() directly.
        # We run it in a separate thread to get a fresh loop.
        with ThreadPoolExecutor() as executor:
            text = executor.submit(asyncio.run, _generate()).result()
        
        # Clean up markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        text = text.strip()
        
        memories = json.loads(text)
        if isinstance(memories, list):
            return memories
            
    except Exception as e:
        LOGGER.error(f"Error extracting memories: {e}")
        
    return []
