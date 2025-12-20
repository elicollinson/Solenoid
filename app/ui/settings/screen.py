# app/ui/settings/screen.py
"""
Settings screen for viewing and editing application configuration.

Provides a modal interface for:
1. Selecting a settings section with arrow keys
2. Editing the YAML content in a textarea
3. Validating changes before saving
4. Optional backend restart after saving
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea, Button, OptionList
from textual.widgets.option_list import Option
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual import on, work
from textual.message import Message

from app.settings.manager import get_settings_manager, SectionInfo


class RestartConfirmScreen(ModalScreen[bool]):
    """
    Modal confirmation screen for backend restart.

    Returns True if user confirms restart, False otherwise.
    """

    CSS = """
    RestartConfirmScreen {
        align: center middle;
    }

    #restart-dialog {
        width: 60;
        height: auto;
        max-height: 16;
        background: $surface;
        border: thick $warning;
        padding: 1 2;
    }

    #restart-title {
        text-align: center;
        text-style: bold;
        height: 3;
        content-align: center middle;
        background: $warning;
        color: $text;
    }

    #restart-message {
        height: auto;
        padding: 1;
        text-align: center;
    }

    #restart-status {
        height: auto;
        padding: 0 1;
        text-align: center;
        color: $text-muted;
        display: none;
    }

    #restart-status.visible {
        display: block;
    }

    #restart-buttons {
        height: auto;
        align: center middle;
        padding: 1 0;
    }

    #restart-buttons Button {
        margin: 0 1;
        min-width: 12;
    }

    #restart-buttons.hidden {
        display: none;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._restarting = False

    def compose(self) -> ComposeResult:
        with Container(id="restart-dialog"):
            yield Static("Restart Backend?", id="restart-title")
            yield Static(
                "Settings have been saved. Restart the backend now to apply changes?",
                id="restart-message"
            )
            yield Static("", id="restart-status")
            with Horizontal(id="restart-buttons"):
                yield Button("Restart Now", id="restart-yes", variant="warning")
                yield Button("Later", id="restart-no", variant="default")

    @on(Button.Pressed, "#restart-yes")
    def on_restart_yes(self) -> None:
        """Handle restart confirmation."""
        if self._restarting:
            return
        self._restarting = True
        self._do_restart()

    @on(Button.Pressed, "#restart-no")
    def on_restart_no(self) -> None:
        """Handle restart decline."""
        if not self._restarting:
            self.dismiss(False)

    def _show_status(self, message: str) -> None:
        """Show status message during restart."""
        status = self.query_one("#restart-status", Static)
        status.update(message)
        status.add_class("visible")

    @work(exclusive=True)
    async def _do_restart(self) -> None:
        """Perform the backend restart in a worker thread."""
        # Hide buttons and show status
        self.query_one("#restart-buttons").add_class("hidden")
        self._show_status("Stopping backend server...")

        try:
            # Import here to avoid circular imports
            from app.server.manager import get_backend_server

            server = get_backend_server()
            if server is None:
                self._show_status("Not running in bundled mode - manual restart required")
                await self._delay_and_dismiss(False)
                return

            self._show_status("Restarting backend server...")

            # Run the restart in a thread to not block the UI
            import asyncio
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, server.restart)

            if success:
                self._show_status("Backend restarted successfully!")
                await self._delay_and_dismiss(True)
            else:
                self._show_status("Restart failed - check logs for details")
                await self._delay_and_dismiss(False)

        except Exception as e:
            self._show_status(f"Error: {str(e)}")
            await self._delay_and_dismiss(False)

    async def _delay_and_dismiss(self, result: bool) -> None:
        """Wait briefly then dismiss the screen."""
        import asyncio
        await asyncio.sleep(1.5)
        self.dismiss(result)


class SettingsScreen(ModalScreen[bool]):
    """
    Modal screen for editing application settings.

    The screen has two modes:
    1. Section selection - arrow keys to navigate, Enter to select
    2. Section editing - TextArea for YAML editing with validation

    Returns True if settings were modified, False otherwise.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back/Close", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-container {
        width: 90%;
        height: 85%;
        max-width: 120;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        layout: vertical;
    }

    #settings-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        height: 3;
        content-align: center middle;
        background: $primary;
        color: $text;
    }

    #section-list {
        height: 1fr;
        border: solid $primary-lighten-2;
        margin: 1 0;
    }

    #section-list:focus {
        border: solid $accent;
    }

    #editor-container {
        display: none;
        height: 1fr;
        margin: 1 0;
    }

    #editor-container.visible {
        display: block;
    }

    #section-selector {
        height: 1fr;
    }

    #section-selector.hidden {
        display: none;
    }

    #section-header {
        height: 3;
        background: $primary-darken-1;
        content-align: center middle;
        padding: 0 1;
        text-style: bold;
    }

    #section-description {
        height: 2;
        color: $text-muted;
        padding: 0 1;
    }

    #yaml-editor {
        height: 1fr;
        min-height: 8;
        border: solid $primary-lighten-2;
    }

    #yaml-editor:focus {
        border: solid $accent;
    }

    #error-message {
        height: auto;
        max-height: 4;
        color: $error;
        background: $error 10%;
        padding: 0 1;
        display: none;
    }

    #error-message.visible {
        display: block;
    }

    #success-message {
        height: auto;
        color: $success;
        background: $success 10%;
        padding: 0 1;
        display: none;
    }

    #success-message.visible {
        display: block;
    }

    #button-bar {
        height: auto;
        min-height: 3;
        align: center middle;
        dock: bottom;
        background: $surface;
        padding: 1 0;
        border-top: solid $primary-lighten-2;
    }

    #button-bar Button {
        margin: 0 1;
        min-width: 16;
    }

    #save-button {
        display: none;
    }

    #save-button.visible {
        display: block;
    }

    #back-button {
        display: none;
    }

    #back-button.visible {
        display: block;
    }

    #close-button.hidden {
        display: none;
    }

    .hint-text {
        color: $text-muted;
        text-style: italic;
        height: 2;
        padding: 0 1;
        content-align: center middle;
    }
    """

    class SettingsChanged(Message):
        """Posted when settings are successfully saved."""
        def __init__(self, section: str) -> None:
            self.section = section
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self._manager = get_settings_manager()
        self._current_section: str | None = None
        self._modified = False

    def compose(self) -> ComposeResult:
        with Container(id="settings-container"):
            yield Static("Settings", id="settings-title")

            # Section selector view
            with Vertical(id="section-selector"):
                yield OptionList(id="section-list")
                yield Static("Press Enter to edit, Escape to close", classes="hint-text")

            # Editor view (hidden initially)
            with Vertical(id="editor-container"):
                yield Static("", id="section-header")
                yield Static("", id="section-description")
                yield TextArea(id="yaml-editor", language="yaml")
                yield Static("", id="error-message")
                yield Static("", id="success-message")

            # Button bar - always visible
            with Horizontal(id="button-bar"):
                yield Button("Back", id="back-button", variant="default")
                yield Button("Save (Ctrl+S)", id="save-button", variant="primary")
                yield Button("Close (Esc)", id="close-button", variant="default")

    def on_mount(self) -> None:
        """Populate the section list on mount."""
        self._populate_sections()
        # Focus the section list
        self.query_one("#section-list", OptionList).focus()

    def _populate_sections(self) -> None:
        """Populate the option list with available settings sections."""
        option_list = self.query_one("#section-list", OptionList)
        option_list.clear_options()

        sections = self._manager.get_all_sections_info()
        for section in sections:
            option_list.add_option(Option(
                f"{section.display_name}",
                id=section.key
            ))

    @on(OptionList.OptionSelected, "#section-list")
    def on_section_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle section selection from the list."""
        if event.option_id:
            self._open_section_editor(str(event.option_id))

    def _open_section_editor(self, section_key: str) -> None:
        """Open the editor for a specific section."""
        self._current_section = section_key
        section_info = self._manager.get_section_info(section_key)

        # Update header and description
        header = self.query_one("#section-header", Static)
        header.update(f"Editing: {section_info.display_name}")

        description = self.query_one("#section-description", Static)
        description.update(section_info.description)

        # Load current YAML content
        yaml_content = self._manager.get_section_as_yaml(section_key)
        editor = self.query_one("#yaml-editor", TextArea)
        editor.load_text(yaml_content)

        # Clear any previous messages
        self._clear_messages()

        # Switch views
        self.query_one("#section-selector").add_class("hidden")
        self.query_one("#editor-container").add_class("visible")
        self.query_one("#back-button").add_class("visible")
        self.query_one("#save-button").add_class("visible")
        self.query_one("#close-button").add_class("hidden")

        # Focus the editor
        editor.focus()

    def _close_section_editor(self) -> None:
        """Close the editor and return to section list."""
        self._current_section = None
        self._clear_messages()

        # Switch views
        self.query_one("#section-selector").remove_class("hidden")
        self.query_one("#editor-container").remove_class("visible")
        self.query_one("#back-button").remove_class("visible")
        self.query_one("#save-button").remove_class("visible")
        self.query_one("#close-button").remove_class("hidden")

        # Focus the section list
        self.query_one("#section-list", OptionList).focus()

    def _clear_messages(self) -> None:
        """Clear error and success messages."""
        error = self.query_one("#error-message", Static)
        error.update("")
        error.remove_class("visible")

        success = self.query_one("#success-message", Static)
        success.update("")
        success.remove_class("visible")

    def _show_error(self, message: str) -> None:
        """Display an error message."""
        self._clear_messages()
        error = self.query_one("#error-message", Static)
        error.update(f"Error: {message}")
        error.add_class("visible")

    def _show_success(self, message: str) -> None:
        """Display a success message."""
        self._clear_messages()
        success = self.query_one("#success-message", Static)
        success.update(message)
        success.add_class("visible")

    @on(Button.Pressed, "#back-button")
    def on_back_pressed(self) -> None:
        """Handle back button press."""
        self._close_section_editor()

    @on(Button.Pressed, "#close-button")
    def on_close_pressed(self) -> None:
        """Handle close button press."""
        self.dismiss(self._modified)

    @on(Button.Pressed, "#save-button")
    def on_save_pressed(self) -> None:
        """Handle save button press."""
        self._save_current_section()

    def _save_current_section(self) -> None:
        """Validate and save the current section."""
        if not self._current_section:
            return

        editor = self.query_one("#yaml-editor", TextArea)
        yaml_content = editor.text

        # Validate and save
        result = self._manager.update_section(self._current_section, yaml_content)

        if result.is_valid:
            self._modified = True
            self._show_success("Settings saved! Checking restart...")
            self.post_message(self.SettingsChanged(self._current_section))
            # Prompt for backend restart
            self._prompt_restart()
        else:
            # Show first error
            error_msg = result.first_error or "Validation failed"
            self._show_error(error_msg)
            # Re-focus editor for correction
            editor.focus()

    def _prompt_restart(self) -> None:
        """Show the restart confirmation dialog."""
        def on_restart_complete(restarted: bool) -> None:
            """Callback when restart dialog is dismissed."""
            if restarted:
                self._show_success("Settings saved and backend restarted!")
            else:
                self._show_success("Settings saved. Restart manually to apply all changes.")

        self.app.push_screen(RestartConfirmScreen(), on_restart_complete)

    def action_save(self) -> None:
        """Handle Ctrl+S - save current section."""
        if self._current_section:
            self._save_current_section()

    def action_cancel(self) -> None:
        """Handle escape key - go back or close."""
        if self._current_section:
            self._close_section_editor()
        else:
            self.dismiss(self._modified)
