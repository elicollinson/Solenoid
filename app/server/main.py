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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint

from app.agent.prime_agent.user_proxy import root_agent
from app.agent.memory.adk_sqlite_memory import SqliteMemoryService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Enable debug logging for AG-UI middleware components if needed
# logging.getLogger('event_translator').setLevel(logging.DEBUG)
# logging.getLogger('endpoint').setLevel(logging.DEBUG)
# logging.getLogger('session_manager').setLevel(logging.DEBUG)

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
    return {
        "name": "Local General Agent API",
        "version": "0.1.0",
        "protocol": "AG-UI",
        "endpoints": {
            "agent": "/api/agent",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
        "agent_hierarchy": [
            "user_proxy_agent (gateway)",
            "├── prime_agent (router)",
            "    └── planning_agent (coordinator)",
            "        ├── code_executor_agent",
            "        ├── chart_generator_agent",
            "        ├── research_agent",
            "        ├── mcp_agent",
            "        └── generic_executor_agent",
        ],
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
