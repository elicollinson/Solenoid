from textual.widgets import TextArea
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
        if event.key == "enter":  # plain Enter = send
            event.prevent_default()
            text = self.text.rstrip()
            if text:
                self.post_message(self.Submitted(text))
                self.text = "" 
        elif event.key in ("ctrl+j", "shift+enter"):
            event.prevent_default()
            self.insert("\n")
