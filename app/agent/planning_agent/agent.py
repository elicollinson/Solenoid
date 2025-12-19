# planning_agent/agent.py
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.code_executor_agent.agent import code_executor_agent
from app.agent.chart_generator_agent.agent import chart_generator_agent
from app.agent.research_agent.agent import research_agent
from app.agent.planning_agent.generic_executor import generic_executor_agent
from app.agent.mcp_agent.agent import mcp_agent

LOGGER = logging.getLogger(__name__)

# Load prompt template from settings
PLANNER_PROMPT = get_agent_prompt("planning_agent")

def get_dynamic_instruction(*args, **kwargs):
    LOGGER.info(f"get_dynamic_instruction called with args={args} kwargs={kwargs}")
    
    # Handle different call signatures
    context = None
    if len(args) > 0:
        context = args[0]
    
    # If context is not what we expect, try to find session in kwargs or args
    session = None
    if hasattr(context, 'session'):
        session = context.session
    elif len(args) > 1:
        # Old signature: agent, session
        session = args[1]
    
    if not session:
        LOGGER.warning("Could not find session in get_dynamic_instruction arguments")
        return PLANNER_PROMPT.format(plan_state="[]")

    # Fetch the plan from session state (defaults to "No plan yet")
    current_plan = session.state.get("plan", "[]")
    
    # Format the prompt with the current plan
    return PLANNER_PROMPT.format(plan_state=current_plan)

# Define the Agent
agent = Agent(
    name="planning_agent",
    model=get_model("agent"), # Using the 'agent' model config, typically a smarter model
    instruction=get_dynamic_instruction, # Use the dynamic instruction function
    sub_agents=[code_executor_agent, chart_generator_agent, research_agent, generic_executor_agent, mcp_agent]
)

planning_agent = agent

