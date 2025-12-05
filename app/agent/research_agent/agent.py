
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.search.universal_search import create_universal_search_tool
from app.agent.search.web_retrieval import read_webpage_tool

LOGGER = logging.getLogger(__name__)

# Create the search tool
search_tool = create_universal_search_tool()

agent = Agent(
    name="research_agent",
    model=get_model("agent"),
    instruction="""
    You are the Research Specialist.
    Your goal is to perform deep research on topics using web search and page retrieval.
    
    TOOLS:
    1. universal_search: Search the web for information.
    2. read_webpage: Read the content of a specific URL.
    
    PROCESS:
    1. Search for relevant pages using `universal_search`.
    2. Read the most promising pages to get details using `read_webpage`.
    3. Synthesize the information.
    4. Return a comprehensive summary to the planner.
    """,
    tools=[search_tool, read_webpage_tool]
)

research_agent = agent
