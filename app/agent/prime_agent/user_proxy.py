# app/agent/prime_agent/user_proxy.py
"""
User Proxy Agent - The gateway between the user and the agent system.

This is the entry point for all user interactions. Memory callbacks are configured here:
- inject_memories: Injects relevant memories into the prompt (before model)
- save_memories_on_final_response: Saves memories when final output is detected (after model)
"""

import logging
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from app.agent.models.factory import get_model
from app.agent.config import get_agent_prompt
from app.agent.callbacks.memory import inject_memories, save_memories_on_final_response
from .agent import agent as prime_agent

LOGGER = logging.getLogger(__name__)

# Load prompt template from settings
USER_PROXY_PROMPT = get_agent_prompt("user_proxy_agent")


def capture_user_query(callback_context: CallbackContext, llm_request):
    """Capture the initial user query and store it in session state."""
    if "original_user_query" not in callback_context.session.state:
        user_text = ""
        if llm_request.contents:
            for content in llm_request.contents:
                if content.parts:
                    for part in content.parts:
                        if part.text:
                            user_text += part.text + "\n"
        user_text = user_text.strip()
        if user_text:
            callback_context.session.state["original_user_query"] = user_text
            LOGGER.info(f"Captured original user query: {user_text[:100]}...")


def get_dynamic_instruction(context, *args, **kwargs):
    """Generate dynamic instruction with the original user request."""
    session = None
    if hasattr(context, 'session'):
        session = context.session
    elif len(args) > 0 and hasattr(args[0], 'session'):
        session = args[0].session

    if not session:
        original_request = "Unknown request"
    else:
        original_request = session.state.get("original_user_query", "Unknown request")

    return USER_PROXY_PROMPT.format(original_request=original_request)


agent = Agent(
    name="user_proxy_agent",
    model=get_model("user_proxy_agent"),
    instruction=get_dynamic_instruction,
    # Memory injection happens at entry point (before model call)
    before_model_callback=[capture_user_query, inject_memories],
    # Memory storage happens when final response is detected
    after_model_callback=[save_memories_on_final_response],
    sub_agents=[prime_agent]
)

root_agent = agent
