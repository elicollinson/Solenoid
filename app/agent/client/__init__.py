from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types   
from app.agent.models.granite import get_granite_model
from typing import Optional    

class ADKClient:
    """Wraps a single 'helper' agent and a Runner with in-memory session storage."""

    def __init__(
        self,
        *,
        app_name: str = "TextualADKChat",
        model: str = "gemini-2.5-flash",
        instruction: str = (
            "You are a concise, helpful assistant. Prefer Markdown for lists, tables, and code."
        ),
        user_id: str = "local",
        session_id: str = "default",
    ):

        # 1) Define a basic LLM Agent (ADK) using Gemini model & an instruction
        self.agent = Agent(
            name="helper",
            model=get_granite_model(),
            instruction=instruction,
        )
        # 2) Session service to preserve context across turns (in memory)
        self.session_service = InMemorySessionService()
        self.session_service.create_session_sync(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        # 3) Runner orchestrates agent execution and yields Event objects
        self.runner = Runner(
            agent=self.agent,
            app_name=app_name,
            session_service=self.session_service,
        )
        self.user_id = user_id
        self.session_id = session_id

    def ask(self, prompt: str) -> str:
        """Run the agent and return the final Markdown string."""
        # Build a Gemini Content message for the user prompt
        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

        final_text: Optional[str] = None
        last_text_seen: Optional[str] = None

        # Runner.run(...) yields a stream of ADK Event objects during the turn
        for event in self.runner.run(
            user_id=self.user_id,
            session_id=self.session_id,
            new_message=msg,
        ):
            # Keep track of any textual content we see
            if event.content and event.content.parts:
                part = event.content.parts[0]
                if getattr(part, "text", None):
                    last_text_seen = part.text

            # When ADK marks an event as the final response, prefer it
            if getattr(event, "is_final_response", None) and event.is_final_response():
                if event.content and event.content.parts:
                    part = event.content.parts[0]
                    if getattr(part, "text", None):
                        final_text = part.text
                # If final event didn't contain text (edge case), we'll fall back below

        return (final_text or last_text_seen or "_(no response)_").strip()