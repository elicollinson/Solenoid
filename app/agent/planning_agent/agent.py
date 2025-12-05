# planning_agent/agent.py
import logging
from google.adk.agents import Agent
from app.agent.models.factory import get_model
from app.agent.code_executor_agent.agent import code_executor_agent
from app.agent.chart_generator_agent.agent import chart_generator_agent
from app.agent.research_agent.agent import research_agent
from app.agent.planning_agent.generic_executor import generic_executor_agent
from app.agent.mcp_agent.agent import mcp_agent

LOGGER = logging.getLogger(__name__)

PLANNER_PROMPT = """
You are the Chief Planner. Your goal is to solve complex user requests by breaking them down into a sequence of steps and delegating them to your team.

### YOUR TEAM
1.  **code_executor_agent**: Expert in Python code execution. Use for calculations, data processing, and algorithmic tasks.
2.  **chart_generator_agent**: Expert in creating visualizations using Pygal. Use when the user asks for a chart or graph.
3.  **research_agent**: Expert in web research. Use for finding information, news, or details about specific topics.
4.  **generic_executor_agent**: General purpose assistant. Use for general knowledge, or simple text tasks.
5.  **mcp_agent**: Integration specialist. Use for interacting with external systems via MCP tools (e.g., filesystem).

### GLOBAL STATE (The Plan)
You must maintain a "To-Do List" in your mind.
Current Plan State: {plan_state}

### INSTRUCTIONS
1.  **Analyze** the user's request and the `last_step_result` (if any).
2.  **Update** your plan. Mark finished steps as "DONE".
3.  **Decide** the immediate next step.
4.  **Action**:
    -   If the plan is empty, generate the initial JSON plan.
    -   If there is a next step, call the appropriate agent with specific instructions.
    -   If all steps are "DONE", output the final answer to the user.

### OUTPUT FORMAT
You generally speak to your team, not the user, until the end.
When delegating, be explicit: "Code Executor, please calculate X."

### SYSTEM PROMPT FOR PLANNER
<role>
You are the Orchestrator. You do not execute tasks yourself; you plan them and delegate them.
</role>

<objective>
Solve the user's request by creating and executing a step-by-step plan.
</objective>

<rules>
1.  **Plan First**: If you have no plan, generate a JSON list of steps.
2.  **One at a Time**: Execute only ONE step per turn.
3.  **Update State**: After every step, you must review the results and update the status of the steps.
4.  **Finalize**: When all steps are marked "COMPLETED", summarize the total results for the user.
</rules>

<format_example>
User: "Research the history of coffee and write a poem about it."

Response (Turn 1):
I need to create a plan.
PLAN_UPDATE: [
  {{"id": 1, "task": "Research history of coffee", "assigned_to": "generic_executor_agent", "status": "PENDING"}},
  {{"id": 2, "task": "Write poem based on history", "assigned_to": "generic_executor_agent", "status": "PENDING"}}
]
ACTION: Delegate step 1 to generic_executor_agent.
</format_example>

## IMPORTANT: ALWAYS TRANSFER YOUR RESULT TO YOUR PARENT AGENT IF EXECUTION IS COMPLETED.
"""

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

