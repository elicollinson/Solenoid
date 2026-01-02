# app/ui/create_agent/screen.py
"""
Agent creation wizard screen - Deterministic multi-step flow.

Steps:
1. Description - User describes what agent they want
2. Plan Review - LLM generates plan, user approves or edits
3. Source Selection - LLM finds sources, user selects which to include
4. Creation - Creates agent and ingests selected sources
5. Complete - Shows summary

Each step has clear UI controls and progress indicators.
"""

import httpx
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import (
    Static, TextArea, Button, Label, Checkbox,
    ProgressBar, LoadingIndicator, ListView, ListItem
)
from textual.containers import Vertical, Horizontal, Container, VerticalScroll
from textual.binding import Binding
from textual import on, work


class SourceItem(ListItem):
    """A selectable source item with checkbox."""

    def __init__(self, url: str, title: str = "", topic: str = "") -> None:
        super().__init__()
        self.url = url
        self.title = title or url
        self.topic = topic
        self.selected = True

    def compose(self) -> ComposeResult:
        with Horizontal(classes="source-item"):
            yield Checkbox(value=True, id=f"cb-{hash(self.url)}")
            with Vertical(classes="source-info"):
                yield Static(self.title, classes="source-title")
                yield Static(self.url, classes="source-url")


class CreateAgentScreen(ModalScreen[bool]):
    """
    Deterministic multi-step wizard for creating custom agents.

    Returns True if agent was created, False if cancelled.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    CSS = """
    CreateAgentScreen {
        align: center middle;
    }

    #wizard-container {
        width: 95%;
        height: 90%;
        max-width: 120;
        background: $surface;
        border: thick $success;
        padding: 1 2;
    }

    #wizard-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        height: 3;
        content-align: center middle;
        background: $success;
        color: $text;
    }

    #step-indicator {
        height: 2;
        text-align: center;
        color: $text-muted;
        padding: 0 1;
    }

    .step-container {
        height: 1fr;
        padding: 1;
        display: none;
    }

    .step-container.active {
        display: block;
    }

    .step-label {
        height: 2;
        color: $primary;
        text-style: bold;
        padding: 0 1;
    }

    #description-input {
        height: 8;
        margin: 1 0;
        border: solid $success-lighten-2;
    }

    #description-input:focus {
        border: solid $accent;
    }

    .hint-text {
        color: $text-muted;
        text-style: italic;
        padding: 0 1;
        height: auto;
    }

    #plan-display {
        height: 1fr;
        padding: 1;
        background: $surface-darken-1;
        overflow-y: auto;
    }

    #sources-list {
        height: 1fr;
        border: solid $primary-lighten-2;
        padding: 1;
        overflow-y: auto;
    }

    .source-item {
        height: auto;
        min-height: 3;
        padding: 0 1;
        margin-bottom: 0;
        background: $surface-darken-1;
    }

    .source-item Checkbox {
        width: 4;
        height: 3;
    }

    .source-text {
        width: 1fr;
        height: auto;
        padding-left: 1;
    }

    .source-topic {
        color: $success;
        text-style: bold;
        height: 2;
        padding: 1 0 0 0;
        margin-top: 1;
    }

    .source-title {
        color: $text;
        height: 1;
    }

    .source-url {
        color: $text-muted;
        height: 1;
    }

    #progress-container {
        height: auto;
        padding: 2;
    }

    #progress-status {
        height: 2;
        text-align: center;
        color: $warning;
    }

    #progress-bar {
        height: 1;
        margin: 1 2;
    }

    #progress-detail {
        height: auto;
        color: $text-muted;
        text-align: center;
    }

    #completion-summary {
        height: 1fr;
        padding: 2;
        background: $success 10%;
    }

    #error-message {
        height: auto;
        padding: 1;
        color: $error;
        background: $error 10%;
        display: none;
    }

    #error-message.visible {
        display: block;
    }

    #button-bar {
        height: 3;
        width: 100%;
        align: center middle;
        background: $surface-lighten-1;
        margin-top: 1;
    }

    #button-bar Button {
        margin: 0 1;
        min-width: 16;
    }

    #loading-container {
        height: 3;
        content-align: center middle;
        display: none;
    }

    #loading-container.visible {
        display: block;
    }

    .checkbox-bar {
        height: 2;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._step = 1  # 1=description, 2=plan, 3=sources, 4=creating, 5=complete
        self._description = ""
        self._plan_data: dict = {}
        self._sources: list[dict] = []
        self._selected_sources: list[str] = []
        self._created_agent_name = ""

    def compose(self) -> ComposeResult:
        with Container(id="wizard-container"):
            yield Static("Create Custom Agent", id="wizard-title")
            yield Static("Step 1 of 4: Describe Your Agent", id="step-indicator")

            # Step 1: Description
            with Vertical(id="step-1", classes="step-container active"):
                yield Label("What kind of agent do you want to create?", classes="step-label")
                yield TextArea(id="description-input")
                yield Static(
                    "Describe the agent's expertise, domain, and what tasks it should handle. "
                    "Be specific - this helps generate better instructions and find relevant sources.",
                    classes="hint-text"
                )

            # Step 2: Plan Review
            with Vertical(id="step-2", classes="step-container"):
                yield Label("Review Generated Plan", classes="step-label")
                yield VerticalScroll(Static("", id="plan-content"), id="plan-display")
                yield Static(
                    "Review the generated configuration. Click 'Approve' to continue or 'Back' to modify your description.",
                    classes="hint-text"
                )

            # Step 3: Source Selection
            with Vertical(id="step-3", classes="step-container"):
                yield Label("Select Knowledge Base Sources", classes="step-label")
                with Horizontal(classes="checkbox-bar"):
                    yield Button("Select All", id="select-all-btn", variant="default")
                    yield Button("Deselect All", id="deselect-all-btn", variant="default")
                yield VerticalScroll(id="sources-list")
                yield Static(
                    "Select which sources to include in the agent's knowledge base.",
                    classes="hint-text"
                )

            # Step 4: Creating
            with Vertical(id="step-4", classes="step-container"):
                yield Label("Creating Agent...", classes="step-label")
                with Vertical(id="progress-container"):
                    yield Static("Initializing...", id="progress-status")
                    yield ProgressBar(id="progress-bar", total=100)
                    yield Static("", id="progress-detail")

            # Step 5: Complete
            with Vertical(id="step-5", classes="step-container"):
                yield Label("Agent Created Successfully!", classes="step-label")
                yield VerticalScroll(Static("", id="completion-content"), id="completion-summary")

            # Loading indicator (shown during API calls)
            with Container(id="loading-container"):
                yield LoadingIndicator()
                yield Static("Working...", id="loading-text")

            # Error message
            yield Static("", id="error-message")

            # Button bar
            with Horizontal(id="button-bar"):
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Back", id="back-btn", variant="default")
                yield Button("Next", id="next-btn", variant="primary")

    def on_mount(self) -> None:
        """Initialize the wizard."""
        description_input = self.query_one("#description-input", TextArea)
        description_input.load_text(
            "I want an agent that specializes in...\n\n"
            "It should be able to help with:\n"
            "- \n"
            "- \n"
        )
        description_input.focus()
        self._update_ui()

    def _update_ui(self) -> None:
        """Update UI based on current step."""
        # Update step indicator
        step_names = {
            1: "Step 1 of 4: Describe Your Agent",
            2: "Step 2 of 4: Review Plan",
            3: "Step 3 of 4: Select Sources",
            4: "Step 4 of 4: Creating Agent",
            5: "Complete!"
        }
        self.query_one("#step-indicator", Static).update(step_names.get(self._step, ""))

        # Show/hide step containers
        for i in range(1, 6):
            container = self.query_one(f"#step-{i}")
            if i == self._step:
                container.add_class("active")
            else:
                container.remove_class("active")

        # Update buttons
        cancel_btn = self.query_one("#cancel-btn", Button)
        back_btn = self.query_one("#back-btn", Button)
        next_btn = self.query_one("#next-btn", Button)

        # Configure buttons for each step
        if self._step == 1:
            cancel_btn.display = True
            back_btn.display = False
            next_btn.label = "Generate Plan"
            next_btn.display = True
        elif self._step == 2:
            cancel_btn.display = True
            back_btn.display = True
            next_btn.label = "Approve & Find Sources"
            next_btn.display = True
        elif self._step == 3:
            cancel_btn.display = True
            back_btn.display = True
            next_btn.label = "Create Agent"
            next_btn.display = True
        elif self._step == 4:
            cancel_btn.display = False
            back_btn.display = False
            next_btn.display = False
        elif self._step == 5:
            cancel_btn.display = False
            back_btn.display = False
            next_btn.label = "Done"
            next_btn.display = True

    def _show_loading(self, message: str = "Working...") -> None:
        """Show loading indicator."""
        container = self.query_one("#loading-container")
        container.add_class("visible")
        self.query_one("#loading-text", Static).update(message)
        self.query_one("#next-btn", Button).disabled = True
        self.query_one("#back-btn", Button).disabled = True

    def _hide_loading(self) -> None:
        """Hide loading indicator."""
        container = self.query_one("#loading-container")
        container.remove_class("visible")
        self.query_one("#next-btn", Button).disabled = False
        self.query_one("#back-btn", Button).disabled = False

    def _show_error(self, message: str) -> None:
        """Show error message."""
        error = self.query_one("#error-message", Static)
        error.update(f"Error: {message}")
        error.add_class("visible")

    def _hide_error(self) -> None:
        """Hide error message."""
        self.query_one("#error-message", Static).remove_class("visible")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self) -> None:
        """Handle cancel button."""
        self.dismiss(False)

    @on(Button.Pressed, "#back-btn")
    def on_back(self) -> None:
        """Handle back button."""
        self._hide_error()
        if self._step > 1:
            self._step -= 1
            self._update_ui()

    @on(Button.Pressed, "#next-btn")
    def on_next(self) -> None:
        """Handle next button."""
        self._hide_error()
        if self._step == 1:
            self._submit_description()
        elif self._step == 2:
            self._approve_plan()
        elif self._step == 3:
            self._create_agent()
        elif self._step == 5:
            self.dismiss(True)

    @on(Button.Pressed, "#select-all-btn")
    def on_select_all(self) -> None:
        """Select all sources."""
        for checkbox in self.query("#sources-list Checkbox"):
            checkbox.value = True

    @on(Button.Pressed, "#deselect-all-btn")
    def on_deselect_all(self) -> None:
        """Deselect all sources."""
        for checkbox in self.query("#sources-list Checkbox"):
            checkbox.value = False

    def _submit_description(self) -> None:
        """Validate and submit description to generate plan."""
        description_input = self.query_one("#description-input", TextArea)
        self._description = description_input.text.strip()

        if len(self._description) < 30:
            self._show_error("Please provide a more detailed description (at least 30 characters)")
            return

        self._generate_plan()

    @work(exclusive=True)
    async def _generate_plan(self) -> None:
        """Call API to generate agent plan."""
        self._show_loading("Generating agent plan...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/agent-wizard/plan",
                    json={"description": self._description},
                    timeout=60.0,
                )
                data = response.json()

            if data.get("status") == "success":
                self._plan_data = data.get("plan", {})
                self._display_plan()
                self._step = 2
                self._update_ui()
            else:
                self._show_error(data.get("message", "Failed to generate plan"))

        except Exception as e:
            self._show_error(str(e))
        finally:
            self._hide_loading()

    def _display_plan(self) -> None:
        """Display the generated plan."""
        plan = self._plan_data
        content = f"""**Agent Name:** `{plan.get('name', 'unknown')}`

**Description:** {plan.get('description', '')}

**System Instruction:**
```
{plan.get('instruction', '')[:500]}{'...' if len(plan.get('instruction', '')) > 500 else ''}
```

**Research Topics for Knowledge Base:**
"""
        for topic in plan.get('research_topics', []):
            content += f"- {topic}\n"

        self.query_one("#plan-content", Static).update(content)

    def _approve_plan(self) -> None:
        """Approve plan and start research."""
        self._research_sources()

    @work(exclusive=True)
    async def _research_sources(self) -> None:
        """Call API to research sources."""
        self._show_loading("Searching for relevant sources...")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/agent-wizard/research",
                    json={
                        "agent_name": self._plan_data.get("name"),
                        "research_topics": self._plan_data.get("research_topics", []),
                    },
                    timeout=120.0,
                )
                data = response.json()

            if data.get("status") == "success":
                self._sources = data.get("sources", [])
                self._display_sources()
                self._step = 3
                self._update_ui()
            else:
                self._show_error(data.get("message", "Failed to research sources"))

        except Exception as e:
            self._show_error(str(e))
        finally:
            self._hide_loading()

    def _display_sources(self) -> None:
        """Display the found sources with checkboxes."""
        sources_list = self.query_one("#sources-list", VerticalScroll)
        sources_list.remove_children()

        if not self._sources:
            sources_list.mount(Static("No sources found. The agent will be created without initial KB content."))
            return

        # Group sources by topic for cleaner display
        current_topic = None
        for i, source in enumerate(self._sources):
            url = source.get("url", "")
            title = source.get("title", url)
            topic = source.get("topic", "")

            # Show topic header when it changes
            if topic != current_topic:
                current_topic = topic
                topic_label = Static(f"📚 {topic}", classes="source-topic")
                sources_list.mount(topic_label)

            # Truncate title and URL for display
            display_title = title[:70] + "..." if len(title) > 70 else title
            display_url = url[:80] + "..." if len(url) > 80 else url

            # Create checkbox with source info
            container = Horizontal(classes="source-item", id=f"source-{i}")
            sources_list.mount(container)
            container.mount(Checkbox(value=True, id=f"source-cb-{i}"))

            # Source text container
            text_container = Vertical(classes="source-text")
            container.mount(text_container)
            text_container.mount(Static(display_title, classes="source-title"))
            text_container.mount(Static(display_url, classes="source-url"))

    def _get_selected_sources(self) -> list[str]:
        """Get list of selected source URLs."""
        selected = []
        for i, source in enumerate(self._sources):
            try:
                checkbox = self.query_one(f"#source-cb-{i}", Checkbox)
                if checkbox.value:
                    selected.append(source.get("url", ""))
            except Exception:
                pass
        return selected

    def _create_agent(self) -> None:
        """Start agent creation process."""
        self._selected_sources = self._get_selected_sources()
        self._step = 4
        self._update_ui()
        self._execute_creation()

    @work(exclusive=True)
    async def _execute_creation(self) -> None:
        """Call API to create agent and ingest sources."""
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_status = self.query_one("#progress-status", Static)
        progress_detail = self.query_one("#progress-detail", Static)

        try:
            # Step 1: Create agent file
            progress_status.update("Creating agent configuration...")
            progress_bar.progress = 10

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/agent-wizard/create",
                    json={
                        "name": self._plan_data.get("name"),
                        "description": self._plan_data.get("description"),
                        "instruction": self._plan_data.get("instruction"),
                        "urls_to_ingest": self._selected_sources,
                    },
                    timeout=300.0,  # 5 min timeout for ingestion
                )
                data = response.json()

            if data.get("status") == "success":
                self._created_agent_name = data.get("agent_name", "")
                progress_bar.progress = 100
                progress_status.update("Complete!")

                # Show completion summary
                self._display_completion(data)
                self._step = 5
                self._update_ui()
            else:
                self._show_error(data.get("message", "Failed to create agent"))
                self._step = 3  # Go back to source selection
                self._update_ui()

        except Exception as e:
            self._show_error(str(e))
            self._step = 3
            self._update_ui()

    def _display_completion(self, data: dict) -> None:
        """Display completion summary."""
        agent_name = data.get("agent_name", "")
        chunks_ingested = data.get("chunks_ingested", 0)
        urls_processed = data.get("urls_processed", 0)
        errors = data.get("errors", [])

        content = f"""**Agent `{agent_name}` is ready!**

**Knowledge Base:**
- URLs processed: {urls_processed}
- Chunks ingested: {chunks_ingested}

**How to use:**
The planning agent will automatically delegate relevant tasks to your new agent.

**To add more knowledge later:**
- "Add [URL] to {agent_name}'s knowledge base"
- Use `/kb-stats {agent_name}` to check KB status
"""

        if errors:
            content += "\n**Warnings:**\n"
            for error in errors[:3]:
                content += f"- {error}\n"

        self.query_one("#completion-content", Static).update(content)

    def action_cancel(self) -> None:
        """Handle Escape key."""
        if self._step < 4:  # Can't cancel during creation
            self.dismiss(False)
