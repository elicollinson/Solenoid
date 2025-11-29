# agent_server.py
import asyncio
import logging
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent.models.granite import get_granite_model
from app.agent.memory.adk_sqlite_memory import SqliteMemoryService
from app.agent.memory.search import search_memories
from app.agent.memory.extractor import llm_extractor

LOGGER = logging.getLogger(__name__)

# 1. Define Services
# We use your custom SqliteMemoryService with the LLM extractor
memory_service = SqliteMemoryService(
    db_path="memories.db",
    extractor=llm_extractor
)
session_service = InMemorySessionService()

# 2. Define Callbacks

def inject_memories(callback_context, llm_request):
    """Before model runs: search memories and inject into prompt."""
    try:
        # Extract user text from the llm_request
        user_text = ""
        if llm_request.contents:
            for content in llm_request.contents:
                if content.parts:
                    for part in content.parts:
                        if part.text:
                            user_text += part.text + "\n"
        
        user_text = user_text.strip()
        if not user_text:
            return

        # Search for relevant memories
        # We use the raw search_memories to get text directly
        hits = search_memories(
            memory_service.conn,
            query_text=user_text,
            user_id=callback_context.session.user_id,
            app_name=callback_context.session.app_name,
            top_n=5
        )

        if not hits:
            return

        # Format memories
        memory_text = "\n".join([f"- {text}" for text, score, row in hits])
        
        # Inject into the llm_request
        # We append a new part with the memories to the last content message
        injection = f"\n\nRelevant Memories:\n{memory_text}"
        if llm_request.contents:
             llm_request.contents[-1].parts.append(types.Part.from_text(text=injection))
        
        LOGGER.info(f"Injected {len(hits)} memories into prompt.")

    except Exception as e:
        LOGGER.error(f"Failed to inject memories: {e}")

def save_memories(callback_context, **kwargs):
    """After model runs: extract and save memories (async)."""
    try:
        # We are in a running event loop, so we must use create_task
        loop = asyncio.get_running_loop()
        loop.create_task(memory_service.add_session_to_memory(callback_context.session))
        LOGGER.info("Memory extraction scheduled.")
    except Exception as e:
        LOGGER.error(f"Failed to save memories: {e}")

# 3. Define the Agent
# We pass the memory_service HERE so the Runner can use it natively
agent = Agent(
    name="helper",
    model=get_granite_model(),
    instruction="You are a concise, helpful assistant. Prefer Markdown.",
    before_model_callback=[inject_memories],
    after_model_callback=[save_memories],
)

root_agent = agent