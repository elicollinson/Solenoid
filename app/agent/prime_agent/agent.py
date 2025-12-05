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
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.agents.callback_context import CallbackContext
from mcp import StdioServerParameters
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

def load_mcp_toolsets(config_path="mcp_config.yaml"):
    """Load MCP toolsets from a YAML configuration file."""
    toolsets = []
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        if not config or "mcp_servers" not in config:
            LOGGER.warning(f"No 'mcp_servers' found in {config_path}")
            return []

        for server_name, server_config in config["mcp_servers"].items():
            LOGGER.info(f"Loading MCP server: {server_name}")
            try:
                toolset = McpToolset(
                    connection_params=StdioConnectionParams(
                        server_params=StdioServerParameters(
                            command=server_config["command"],
                            args=server_config["args"]
                        )
                    )
                )
                toolsets.append(toolset)
            except Exception as e:
                LOGGER.error(f"Failed to load MCP server {server_name}: {e}")
                
    except FileNotFoundError:
        LOGGER.warning(f"MCP config file not found at {config_path}")
    except Exception as e:
        LOGGER.error(f"Error loading MCP config: {e}")
        
    return toolsets

# 3. Define the Agent
# We pass the memory_service HERE so the Runner can use it natively
agent = Agent(
    name="prime_agent",
    model=get_model("agent"),
    instruction="""
    You are the Prime Agent, a concise and helpful assistant.
    
    YOUR CAPABILITIES:
    1.  **General Assistance**: Answer simple questions directly.
    2.  **Complex Tasks**: Delegate ANY complex task, multi-step request, code execution, or chart generation to `planning_agent`.
    ## IMPORTANT: ALWAYS TRANSFER YOUR RESULT TO YOUR PARENT AGENT IF EXECUTION IS COMPLETED.
    """,
    before_model_callback=[],
    # after_model_callback=[save_memories],
    tools=load_mcp_toolsets(),
    sub_agents=[planning_agent]
)

root_agent = agent