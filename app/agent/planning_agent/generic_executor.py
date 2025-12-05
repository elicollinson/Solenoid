# generic_executor.py
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
import yaml
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

LOGGER = logging.getLogger(__name__)



# Define the Agent
agent = Agent(
    name="generic_executor_agent",
    model=get_model("agent"),
    instruction="""
    You are a Generic Executor Agent.
    
    YOUR GOAL: Execute general tasks, answer questions, and perform research or analysis as requested by the Planner.
    
    CAPABILITIES:
    - You can use available tools to find information or perform actions.
    - You can answer general knowledge questions.
    - You do NOT execute Python code or generate charts (those are for other specialists).
    
    OUTPUT:
    - Provide concise, direct answers to the Planner's specific request.
    - Do not ask follow-up questions unless absolutely necessary.

    ## IMPORTANT: ALWAYS TRANSFER YOUR RESULT TO YOUR PARENT AGENT IF EXECUTION IS COMPLETED.
    """,
    # tools=load_mcp_toolsets(),
    disallow_transfer_to_peers=True
)

generic_executor_agent = agent
