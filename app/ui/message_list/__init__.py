from textual.containers import VerticalScroll
from textual.widgets import Markdown

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