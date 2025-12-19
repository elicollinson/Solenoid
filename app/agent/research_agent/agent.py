import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.search.universal_search import create_universal_search_tool
from app.agent.search.web_retrieval import read_webpage_tool

LOGGER = logging.getLogger(__name__)

# Create the search tool
search_tool = create_universal_search_tool()

# Load prompt from settings
RESEARCH_AGENT_PROMPT = get_agent_prompt("research_agent")

agent = Agent(
    name="research_agent",
    model=get_model("agent"),
    instruction=RESEARCH_AGENT_PROMPT,
    tools=[search_tool, read_webpage_tool],
    disallow_transfer_to_peers=True,
    disallow_transfer_to_parent=True  # Agent must complete task, not transfer back
)

research_agent = agent
