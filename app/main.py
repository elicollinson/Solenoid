# textual >= 0.4x
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown, TextArea, Header, Footer
from textual import events
from textual.message import Message


class ChatInput(TextArea):
    """Enter submits; Ctrl+J inserts a newline. If your terminal emits 'shift+enter',
    it's handled too, but not all terminals do."""

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()  # <- no sender argument

    def on_key(self, event: events.Key) -> None:
        # Stop TextArea's default behavior when we want to override it.
        # (prevent_default() blocks base handlers)  # docs-backed
        if event.key == "enter":  # plain Enter = send
            event.prevent_default()
            text = self.text.rstrip()
            if text:
                self.post_message(self.Submitted(text))
                self.text = ""  # clear after send
        elif event.key in ("ctrl+j", "shift+enter"):  # reliable newline + best-effort Shift+Enter
            event.prevent_default()
            self.insert("\n")  # TextArea supports insert/replace/delete programmatically


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


class ChatApp(App):
    CSS = """
    Screen { layout: vertical; }
    ChatInput { height: 6; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield MessageList(id="feed")           # <- container first (no lists here)
        yield ChatInput(placeholder="Type…")   # <- multiline input
        yield Footer()

    def on_chat_input_submitted(self, msg: ChatInput.Submitted) -> None:
        self.query_one(MessageList).add(msg.text)


if __name__ == "__main__":
    ChatApp().run()