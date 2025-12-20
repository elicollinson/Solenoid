from textual.widgets import TextArea
from textual import events
from textual.message import Message


class ChatInput(TextArea):
    """Enter submits; Ctrl+J inserts a newline. If your terminal emits 'shift+enter',
    it's handled too, but not all terminals do.

    Supports slash commands - text starting with '/' is posted as a Command message.
    """

    class Submitted(Message):
        """Posted when regular text is submitted."""
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class Command(Message):
        """Posted when a slash command is entered."""
        def __init__(self, command: str, args: str = "") -> None:
            self.command = command  # The command without the leading /
            self.args = args        # Any arguments after the command
            super().__init__()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":  # plain Enter = send
            event.prevent_default()
            text = self.text.rstrip()
            if text:
                # Check if it's a slash command
                if text.startswith("/"):
                    self._handle_command(text)
                else:
                    self.post_message(self.Submitted(text))
                self.text = ""
        elif event.key in ("ctrl+j", "shift+enter"):
            event.prevent_default()
            self.insert("\n")

    def _handle_command(self, text: str) -> None:
        """Parse and post a slash command."""
        # Remove the leading /
        text = text[1:]

        # Split into command and args
        parts = text.split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if command:
            self.post_message(self.Command(command, args))
