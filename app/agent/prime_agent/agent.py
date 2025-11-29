# agent_server.py
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService
from app.agent.models.granite import get_granite_model
from app.agent.memory.adk_sqlite_memory import SqliteMemoryService

# 1. Define Services
# We use your custom SqliteMemoryService
memory_service = SqliteMemoryService(db_path="memories.db")
session_service = InMemorySessionService()

# 2. Define the Agent
# We pass the memory_service HERE so the Runner can use it natively
agent = Agent(
    name="helper",
    model=get_granite_model(),
    instruction="You are a concise, helpful assistant. Prefer Markdown.",
    # If your Agent class supports direct memory injection, add it here.
    # Otherwise, standard ADK uses the Runner to bridge them.
)

root_agent = agent