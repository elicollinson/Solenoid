import logging
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from app.agent.models.factory import get_model
from .agent import agent as prime_agent

LOGGER = logging.getLogger(__name__)

USER_PROXY_PROMPT = """
You are the User Proxy. Your goal is to communicate the final answer to the user.

### ORIGINAL USER REQUEST
"{original_request}"

### INSTRUCTIONS
1.  **Receive Request**: You are the first point of contact.
2.  **Delegate**: Delegate the request to `prime_agent` to solve it.
3.  **Verify**: When `prime_agent` returns with an answer:
    -   Does it fully address the original user request?
4.  **Action**:
    -   **YES**: Output the final answer to the user clearly and concisely.
    -   **NO**: Delegate back to `prime_agent` with specific feedback on what is missing or incorrect.

### OUTPUT FORMAT
If answering the user, just speak naturally.
If transferring, use the standard transfer mechanism.
"""

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
            LOGGER.info(f"Captured original user query: {user_text}")

def get_dynamic_instruction(context, *args, **kwargs):
    # Handle different call signatures if necessary
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
    model=get_model("agent"),
    instruction=get_dynamic_instruction,
    before_model_callback=[capture_user_query],
    sub_agents=[prime_agent]
)

root_agent = agent
