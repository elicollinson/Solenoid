from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, LoadingIndicator
from textual import work
from app.agent.client import ADKClient
from app.ui.message_list import MessageList
from app.ui.chat_input import ChatInput

class AgentApp(App):
    CSS = """
    Screen { layout: vertical; }
    #loading { height: 3; content-align: center middle; display: none; }
    #loading.-visible { display: block; }
    ChatInput { height: 6; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield MessageList(id="feed")
        yield LoadingIndicator(id="loading")
        yield ChatInput(placeholder="Type…")
        yield Footer()

    def on_mount(self) -> None:
        # Create a single helper agent + runner for the entire app session
        self.ai = ADKClient()
        self.loading_indicator = self.query_one("#loading", LoadingIndicator)
        self._set_loading(False)

    def on_chat_input_submitted(self, msg: ChatInput.Submitted) -> None:
        feed = self.query_one(MessageList)
        # Show the user message immediately
        feed.add(f"**You**\n\n{msg.text}")
        self._set_loading(True)
        # Ask the agent in a worker so the UI never blocks
        self._ask_and_render(msg.text)

    @work(thread=True, exclusive=True)  # run in background; one at a time
    def _ask_and_render(self, user_text: str) -> None:
        try:
            md = self.ai.ask(user_text)
        finally:
            self.call_from_thread(self._set_loading, False)
        # UI updates from worker must be marshalled to the main thread
        self.call_from_thread(self._add_assistant_message, md)

    def _set_loading(self, is_loading: bool) -> None:
        indicator = getattr(self, "loading_indicator", None)
        if indicator:
            indicator.set_class(is_loading, "-visible")

    def _add_assistant_message(self, md: str) -> None:
        self.query_one(MessageList).add(f"**Assistant**\n\n{md}")
