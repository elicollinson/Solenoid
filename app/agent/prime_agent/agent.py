# agent_server.py
import asyncio
import logging
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent.models.factory import get_model
from app.agent.memory.adk_sqlite_memory import SqliteMemoryService
from app.agent.memory.search import search_memories
from app.agent.memory.extractor import llm_extractor
import yaml
from google.adk.agents.callback_context import CallbackContext
from app.agent.planning_agent.agent import planning_agent

LOGGER = logging.getLogger(__name__)

# 1. Define Services
# We use your custom SqliteMemoryService with the LLM extractor
memory_service = SqliteMemoryService(
    db_path="memories.db",
    extractor=llm_extractor
)
session_service = InMemorySessionService()

# 2. Define Callbacks

def inject_memories(callback_context: CallbackContext, llm_request):
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
        
        callback_context.session.state["existing_memories"] = memory_text  # Store for extractor use

        # Inject into the llm_request
        # We append a new part with the memories to the last content message
        injection = f"\n\nRelevant Memories:\n{memory_text}"
        if llm_request.contents:
             llm_request.contents[-1].parts.append(types.Part.from_text(text=injection))
        
        LOGGER.info(f"Injected {len(hits)} memories into prompt:")
        for i, (text, score, row) in enumerate(hits, 1):
             LOGGER.info(f"  [{i}] (score={score:.2f}): {text}")

    except Exception as e:
        LOGGER.error(f"Failed to inject memories: {e}")

def save_memories(callback_context, **kwargs):
    """After model runs: extract and save memories (async)."""
    try:
        # Check if we have a response object and if the turn is complete
        llm_response = kwargs.get("llm_response")
        
        # Debug logging to identify correct keys if llm_response isn't what we expect
        LOGGER.info(f"save_memories kwargs keys: {list(kwargs.keys())}")
        if llm_response:
             LOGGER.info(f"llm_response type: {type(llm_response)}")
             LOGGER.info(f"turn_complete: {getattr(llm_response, 'turn_complete', 'N/A')}")
             LOGGER.info(f"finish_reason: {getattr(llm_response, 'finish_reason', 'N/A')}")

        # If we have a response, we only want to save on the final chunk/turn completion
        if llm_response:
            # Check for turn_complete or if it's not a partial chunk
            # LlmResponse has 'turn_complete' field, but it might be None
            is_complete = getattr(llm_response, "turn_complete", False)
            finish_reason = getattr(llm_response, "finish_reason", None)
            
            # If it's not explicitly complete and there's no finish reason, assume it's an intermediate chunk
            if not is_complete and not finish_reason:
                return

        # We are in a running event loop, so we must use create_task
        loop = asyncio.get_running_loop()
        loop.create_task(memory_service.add_session_to_memory(callback_context.session))
        LOGGER.info("Memory extraction scheduled.")
    except Exception as e:
        LOGGER.error(f"Failed to save memories: {e}")

        LOGGER.error(f"Failed to save memories: {e}")



# 3. Define the Agent
# We pass the memory_service HERE so the Runner can use it natively
PRIME_AGENT_PROMPT = """
You are the Prime Agent, the intelligent router of the agent system.

### ROLE
You are the decision-maker that determines whether a request can be answered directly or requires delegation to the planning system. Your goal is efficiency: handle simple tasks instantly, delegate complex ones appropriately.

### DECISION FRAMEWORK

**Answer Directly** (do NOT delegate) when the request is:
-   A factual question answerable from general knowledge
-   A simple explanation or definition
-   A yes/no question with straightforward reasoning
-   A brief opinion or recommendation request
-   Clarification of a previous response

**Delegate to `planning_agent`** when the request involves:
-   Code execution, calculations, or data processing
-   Chart or visualization generation
-   Multi-step tasks requiring coordination
-   Web research or information gathering from external sources
-   File system operations or external integrations
-   Any task requiring specialized tools

### EXAMPLES

| Request | Action |
|---------|--------|
| "What is the capital of France?" | Answer directly: "Paris" |
| "Calculate the factorial of 20" | Delegate → code execution required |
| "Create a bar chart of sales data" | Delegate → chart generation required |
| "Research the latest AI news" | Delegate → web search required |
| "What is machine learning?" | Answer directly: explanation |
| "Analyze this CSV and create a report" | Delegate → multi-step task |

### WORKFLOW
1.  **Analyze**: Read the request carefully.
2.  **Classify**: Determine if it's simple (direct answer) or complex (delegation).
3.  **Execute**:
    -   **Simple**: Provide a clear, accurate, concise response.
    -   **Complex**: Transfer to `planning_agent` with the full context of the request.
4.  **Return**: Always transfer your result back to your parent agent when done.

### CONSTRAINTS
-   NEVER attempt tasks requiring code execution, charts, web search, or file operations yourself.
-   NEVER guess when you can delegate to get an accurate answer.
-   ALWAYS transfer your final result to your parent agent upon completion.
-   Keep direct answers concise but complete.
"""

agent = Agent(
    name="prime_agent",
    model=get_model("agent"),
    instruction=PRIME_AGENT_PROMPT,
    before_model_callback=[],
    # after_model_callback=[save_memories],
    # after_model_callback=[save_memories],
    sub_agents=[planning_agent]
)

root_agent = agent