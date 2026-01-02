"""
AG-UI Protocol compatible FastAPI server for the Google ADK agent.

This module exposes the ADK agent hierarchy as a web API using the AG-UI protocol,
which streams events as Server-Sent Events (SSE) in JSON format.

Usage:
    uvicorn app.server.main:app --host 0.0.0.0 --port 8000

Or run directly:
    python -m app.server.main
"""

import logging
from contextlib import asynccontextmanager

# =============================================================================
# LOGGING CONFIGURATION - MUST happen before any app imports!
# =============================================================================
_log_file = "solenoid.log"
_file_handler = logging.FileHandler(_log_file, mode="a")
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

# Console handler for important logs only (WARNING and above)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("%(levelname)s - %(name)s - %(message)s"))
_console_handler.setLevel(logging.WARNING)

# Root logger: both handlers
logging.root.setLevel(logging.INFO)
logging.root.handlers = [_file_handler, _console_handler]

# Redirect noisy loggers to file ONLY (prevents TUI bleed-through)
# This includes the parent "app.agent" to catch ALL app.agent.* loggers
_noisy_loggers = [
    "httpx", "httpcore", "urllib3", "litellm", "LiteLLM",
    "uvicorn", "uvicorn.error", "uvicorn.access",
    "app.agent",  # Catch-all for ALL app.agent.* loggers
]
for _name in _noisy_loggers:
    _logger = logging.getLogger(_name)
    _logger.handlers = [_file_handler]
    _logger.propagate = False
    _logger.setLevel(logging.DEBUG)  # Capture all to file

logger = logging.getLogger(__name__)

# =============================================================================
# Now safe to import app modules (loggers are already configured)
# =============================================================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint

from app.agent.prime_agent.user_proxy import root_agent
from app.agent.memory.adk_sqlite_memory import SqliteMemoryService
from app.agent.custom_agents.setup import initialize_custom_agents
from app.agent.planning_agent.agent import set_custom_agents

# Default database path for memory service
DEFAULT_MEMORY_DB = "memories.db"

# Initialize memory service (optional - can be None for in-memory sessions)
memory_service: SqliteMemoryService | None = None

try:
    memory_service = SqliteMemoryService(db_path=DEFAULT_MEMORY_DB)
    logger.info(f"SQLite memory service initialized with {DEFAULT_MEMORY_DB}")
except Exception as e:
    logger.warning(f"Could not initialize memory service: {e}. Using in-memory sessions.")
    memory_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown tasks."""
    logger.info("Starting AG-UI server with ADK agent...")

    # Initialize custom agents from agents/ directory
    try:
        custom_agents = initialize_custom_agents()
        set_custom_agents(custom_agents)
        logger.info(f"Loaded {len(custom_agents)} custom agent(s)")
    except Exception as e:
        logger.error(f"Failed to initialize custom agents: {e}")
        # Continue without custom agents - system still functional

    yield
    logger.info("Shutting down AG-UI server...")


# Create the FastAPI application
app = FastAPI(
    title="Local General Agent API",
    description="AG-UI Protocol compatible API for the multi-agent ADK system",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for frontend compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create the AG-UI ADKAgent wrapper
# This wraps the root_agent (user_proxy_agent) which delegates to the full agent hierarchy
adk_agent_wrapper = ADKAgent(
    adk_agent=root_agent,
    app_name="local_general_agent",
    user_id="default_user",  # Can be overridden via headers
    # Session configuration
    session_timeout_seconds=1200,  # 20 minutes
    cleanup_interval_seconds=300,  # 5 minutes
    # Execution timeouts
    execution_timeout_seconds=600,  # 10 minutes for complex multi-agent tasks
    tool_timeout_seconds=300,  # 5 minutes per tool
    max_concurrent_executions=10,
    # Memory service for session persistence (optional)
    memory_service=memory_service,
    use_in_memory_services=memory_service is None,
)

# Add the AG-UI endpoint
# This creates a POST endpoint that accepts AG-UI RunAgentInput and streams SSE events
add_adk_fastapi_endpoint(
    app,
    adk_agent_wrapper,
    path="/api/agent",
)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    from app.agent.custom_agents.registry import get_registry

    # Get custom agent names
    registry = get_registry()
    custom_agent_names = registry.get_agent_names() if registry.is_initialized else []

    # Build hierarchy display
    hierarchy = [
        "user_proxy_agent (gateway)",
        "├── prime_agent (router)",
        "    └── planning_agent (coordinator)",
        "        ├── code_executor_agent",
        "        ├── chart_generator_agent",
        "        ├── research_agent",
        "        ├── mcp_agent",
        "        ├── generic_executor_agent",
    ]

    # Add custom agents
    for i, name in enumerate(custom_agent_names):
        prefix = "        └── " if i == len(custom_agent_names) - 1 else "        ├── "
        hierarchy.append(f"{prefix}{name} (custom)")

    return {
        "name": "Local General Agent API",
        "version": "0.1.0",
        "protocol": "AG-UI",
        "endpoints": {
            "agent": "/api/agent",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
        "agent_hierarchy": hierarchy,
        "custom_agents": custom_agent_names,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/reload-agents")
async def reload_agents():
    """
    Reload custom agents from the agents/ directory.

    This endpoint is called by the /reload-agents TUI command.
    """
    from app.agent.custom_agents.setup import reload_custom_agents
    from app.agent.planning_agent.agent import reload_custom_agents as update_planning_agent

    try:
        # Reload agents from files
        new_agents, errors = reload_custom_agents()

        # Update the planning agent
        update_planning_agent(new_agents)

        return {
            "status": "success",
            "agents_loaded": len(new_agents),
            "agent_names": [a.name for a in new_agents],
            "errors": errors,
        }
    except Exception as e:
        logger.error(f"Failed to reload agents: {e}")
        return {
            "status": "error",
            "message": str(e),
            "agents_loaded": 0,
            "agent_names": [],
            "errors": [str(e)],
        }


@app.get("/api/agents")
async def list_agents():
    """
    List all available agents (built-in and custom).

    This endpoint is called by the /agents TUI command.
    """
    from app.agent.custom_agents.setup import get_custom_agent_list

    builtin_agents = [
        {"name": "code_executor_agent", "type": "builtin", "description": "Executes Python code in WASM sandbox"},
        {"name": "chart_generator_agent", "type": "builtin", "description": "Generates charts using Pygal"},
        {"name": "research_agent", "type": "builtin", "description": "Performs web searches and retrieval"},
        {"name": "mcp_agent", "type": "builtin", "description": "Accesses MCP server tools"},
        {"name": "generic_executor_agent", "type": "builtin", "description": "Handles knowledge tasks"},
    ]

    custom_agents = get_custom_agent_list()

    return {
        "builtin_agents": builtin_agents,
        "custom_agents": custom_agents,
        "total_count": len(builtin_agents) + len(custom_agents),
    }


@app.get("/api/kb/{agent_name}/stats")
async def get_kb_stats(agent_name: str):
    """Get statistics for an agent's knowledge base."""
    from app.agent.knowledge_base import get_kb_manager

    try:
        manager = get_kb_manager()
        stats = manager.get_stats(agent_name)
        return {
            "status": "success",
            "agent_name": stats.agent_name,
            "chunk_count": stats.chunk_count,
            "doc_count": stats.doc_count,
            "total_text_length": stats.total_text_length,
            "has_embeddings": stats.has_embeddings,
            "embedding_count": stats.embedding_count,
        }
    except Exception as e:
        logger.error(f"Failed to get KB stats for {agent_name}: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/kb/{agent_name}/clear")
async def clear_kb(agent_name: str):
    """Clear all data from an agent's knowledge base."""
    from app.agent.knowledge_base import get_kb_manager

    try:
        manager = get_kb_manager()
        count = manager.clear_kb_for_agent(agent_name)
        return {
            "status": "success",
            "agent_name": agent_name,
            "chunks_deleted": count,
        }
    except Exception as e:
        logger.error(f"Failed to clear KB for {agent_name}: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/kb/{agent_name}/ingest")
async def ingest_to_kb(agent_name: str, url: str = None, text: str = None, title: str = None):
    """
    Ingest content into an agent's knowledge base.

    Either url or text must be provided.
    """
    from app.agent.knowledge_base import ingest_url, ingest_text

    try:
        if url:
            result = ingest_url(agent_name, url)
        elif text:
            result = ingest_text(agent_name, text, title=title)
        else:
            return {"status": "error", "message": "Either url or text must be provided"}

        if result.success:
            return {
                "status": "success",
                "doc_id": result.doc_id,
                "title": result.title,
                "chunk_count": result.chunk_count,
                "total_chars": result.total_chars,
            }
        else:
            return {"status": "error", "message": result.error}
    except Exception as e:
        logger.error(f"Failed to ingest to KB for {agent_name}: {e}")
        return {"status": "error", "message": str(e)}


from pydantic import BaseModel
from typing import Optional

class CreateAgentRequest(BaseModel):
    name: str
    yaml_content: str


class WizardPlanRequest(BaseModel):
    description: str


class WizardResearchRequest(BaseModel):
    agent_name: str
    research_topics: list[str]


class WizardCreateRequest(BaseModel):
    name: str
    description: str
    instruction: str
    urls_to_ingest: list[str] = []


@app.post("/api/agent-wizard/plan")
async def wizard_generate_plan(request: WizardPlanRequest):
    """
    Generate an agent plan from user description.

    Uses the LLM to create a structured plan including:
    - Agent name
    - Description
    - System instruction
    - Research topics for KB
    """
    import re
    import json
    import litellm
    from app.agent.config import load_settings

    try:
        # Get model config
        config = load_settings()
        models_config = config.get("models", {})
        default_config = models_config.get("default", {})
        model_name = default_config.get("name", "ministral-3:8b-instruct-2512-q4_K_M")
        provider = default_config.get("provider", "ollama_chat")
        full_model = f"{provider}/{model_name}"

        # Generate plan using LLM
        prompt = f"""Based on this user request, create a plan for a new custom agent.

User Request:
{request.description}

Generate a JSON response with these fields:
- name: lowercase agent name with underscores (e.g., "legal_research_agent")
- description: short description (10-100 chars)
- instruction: detailed system prompt (200-500 chars)
- research_topics: list of 3-5 topics to research for the knowledge base

IMPORTANT: Respond ONLY with valid JSON, no markdown, no explanation.

Example format:
{{"name": "example_agent", "description": "Short description", "instruction": "Detailed system prompt...", "research_topics": ["topic 1", "topic 2", "topic 3"]}}
"""

        # Use format="json" for Ollama models to get proper JSON output
        response = litellm.completion(
            model=full_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            format="json",  # Ollama-specific JSON mode
        )
        response_text = response.choices[0].message.content.strip()

        # Parse the JSON response
        try:
            plan = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}. Response: {response_text[:500]}")
            raise ValueError(f"Model did not return valid JSON: {str(e)}")

        # Validate required fields
        required = ["name", "description", "instruction", "research_topics"]
        for field in required:
            if field not in plan:
                raise ValueError(f"Missing required field: {field}")

        # Validate name format
        name = plan["name"]
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            # Try to fix the name
            name = re.sub(r'[^a-z0-9_]', '_', name.lower())
            name = re.sub(r'_+', '_', name).strip('_')
            if not name or not name[0].isalpha():
                name = "custom_" + name
            plan["name"] = name

        return {
            "status": "success",
            "plan": plan,
        }

    except Exception as e:
        logger.error(f"Failed to generate plan: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/agent-wizard/research")
async def wizard_research_sources(request: WizardResearchRequest):
    """
    Research sources for the agent's knowledge base.

    Searches for relevant URLs for each research topic.
    """
    from app.agent.search.universal_search import universal_search

    try:
        all_sources = []

        for topic in request.research_topics:
            try:
                # Search for this topic
                search_results = universal_search(topic)

                # Parse the search results to extract URLs
                lines = search_results.split('\n')
                current_title = ""

                for line in lines:
                    line = line.strip()
                    if line.startswith("Title:"):
                        current_title = line.replace("Title:", "").strip()
                    elif line.startswith("Link:"):
                        url = line.replace("Link:", "").strip()
                        if url and url.startswith("http"):
                            all_sources.append({
                                "url": url,
                                "title": current_title or url,
                                "topic": topic,
                            })
                            current_title = ""

                            # Limit to 3 sources per topic
                            topic_count = sum(1 for s in all_sources if s["topic"] == topic)
                            if topic_count >= 3:
                                break

            except Exception as e:
                logger.warning(f"Search failed for topic '{topic}': {e}")
                continue

        # Deduplicate by URL
        seen_urls = set()
        unique_sources = []
        for source in all_sources:
            if source["url"] not in seen_urls:
                seen_urls.add(source["url"])
                unique_sources.append(source)

        return {
            "status": "success",
            "sources": unique_sources,
            "topics_searched": len(request.research_topics),
        }

    except Exception as e:
        logger.error(f"Failed to research sources: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/agent-wizard/create")
async def wizard_create_agent(request: WizardCreateRequest):
    """
    Create the agent and populate its knowledge base.

    This is the final step that:
    1. Creates the YAML file
    2. Reloads agents
    3. Ingests selected URLs to KB
    """
    import re
    import yaml
    from app.agent.custom_agents.loader import get_agents_directory
    from app.agent.custom_agents.setup import reload_custom_agents
    from app.agent.planning_agent.agent import reload_custom_agents as update_planning_agent
    from app.agent.knowledge_base import ingest_url

    try:
        # Validate name
        name = request.name
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            return {"status": "error", "message": f"Invalid agent name: {name}"}

        # Check reserved names
        reserved = {
            "user_proxy_agent", "prime_agent", "planning_agent",
            "code_executor_agent", "chart_generator_agent",
            "research_agent", "generic_executor_agent", "mcp_agent",
        }
        if name in reserved:
            return {"status": "error", "message": f"Name '{name}' is reserved"}

        # Check if already exists
        agents_dir = get_agents_directory()
        agent_file = agents_dir / f"{name}.yaml"
        if agent_file.exists():
            return {"status": "error", "message": f"Agent '{name}' already exists"}

        # Build config
        config = {
            "name": name,
            "description": request.description,
            "instruction": request.instruction,
            "tools": ["universal_search", "read_webpage"],
            "mcp_servers": [],
            "knowledge_base": {
                "enabled": True,
                "search_top_k": 10,
                "search_threshold": 0.7,
            },
            "metadata": {
                "author": "wizard",
                "version": 1,
                "tags": [],
            },
            "enabled": True,
        }

        # Create YAML file
        agents_dir.mkdir(parents=True, exist_ok=True)
        yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)
        agent_file.write_text(yaml_content, encoding="utf-8")
        logger.info(f"Created agent file: {agent_file}")

        # Reload agents
        new_agents, reload_errors = reload_custom_agents()
        update_planning_agent(new_agents)

        # Ingest URLs to KB
        total_chunks = 0
        urls_processed = 0
        ingestion_errors = []

        for url in request.urls_to_ingest:
            try:
                result = ingest_url(name, url)
                if result.success:
                    total_chunks += result.chunk_count
                    urls_processed += 1
                else:
                    ingestion_errors.append(f"{url}: {result.error}")
            except Exception as e:
                ingestion_errors.append(f"{url}: {str(e)}")

        return {
            "status": "success",
            "agent_name": name,
            "urls_processed": urls_processed,
            "chunks_ingested": total_chunks,
            "errors": ingestion_errors + reload_errors,
        }

    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/create-agent")
async def create_agent(request: CreateAgentRequest):
    """
    Create a new agent from YAML content.

    This endpoint is called after user approves a proposed agent.
    """
    from app.agent.custom_agents.tools import create_agent_file
    from app.agent.custom_agents.setup import reload_custom_agents
    from app.agent.planning_agent.agent import reload_custom_agents as update_planning_agent

    try:
        # Create the agent file
        result = create_agent_file(request.name, request.yaml_content)

        if result.startswith("Error"):
            return {"status": "error", "message": result}

        # Reload agents to pick up the new one
        new_agents, errors = reload_custom_agents()
        update_planning_agent(new_agents)

        return {
            "status": "success",
            "message": result,
            "agents_loaded": len(new_agents),
            "agent_names": [a.name for a in new_agents],
        }
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
