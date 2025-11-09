from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown, TextArea, Header, Footer
from textual import events
from textual.message import Message
from textual import work
from app.agent.client import ADKClient

# ---------- Your existing widgets ----------
class ChatInput(TextArea):
    """Enter submits; Ctrl+J inserts a newline. If your terminal emits 'shift+enter',
    it's handled too, but not all terminals do."""

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()  # <- no sender argument

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":  # plain Enter = send
            event.prevent_default()
            text = self.text.rstrip()
            if text:
                self.post_message(self.Submitted(text))
                self.text = "" 
        elif event.key in ("ctrl+j", "shift+enter"):
            event.prevent_default()
            self.insert("\n")


class MessageList(VerticalScroll):
    DEFAULT_CSS = """
    MessageList { height: 1fr; padding: 1; }
    MessageList > Markdown { border: round $panel; padding: 1; margin-bottom: 1; }
    """

    def on_mount(self) -> None:
        # Pin to bottom as new content is added until user scrolls up.
        self.anchor(True)

    def add(self, md: str) -> None:
        self.mount(Markdown(md))


# ---------- Your Chat app wired to ADK ----------
class AgentApp(App):
    CSS = """
    Screen { layout: vertical; }
    ChatInput { height: 6; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield MessageList(id="feed")
        yield ChatInput(placeholder="Type…")
        yield Footer()

    def on_mount(self) -> None:
        # Create a single helper agent + runner for the entire app session
        self.ai = ADKClient()

    def on_chat_input_submitted(self, msg: ChatInput.Submitted) -> None:
        feed = self.query_one(MessageList)
        # Show the user message immediately
        feed.add(f"**You**\n\n{msg.text}")
        # Ask the agent in a worker so the UI never blocks
        self._ask_and_render(msg.text)

    @work(thread=True, exclusive=True)  # run in background; one at a time
    def _ask_and_render(self, user_text: str) -> None:
        md = self.ai.ask(user_text)
        # UI updates from worker must be marshalled to the main thread
        self.call_from_thread(self.query_one(MessageList).add, f"**Assistant**\n\n{md}")
