"""Action modal for executing bulk operations on repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Static,
)

from gh_toolkit.core.llm import (
    ADVANCED_LLM_MODEL,
    BALANCED_LLM_MODEL,
    DEFAULT_LLM_MODEL,
)


@dataclass
class ActionResult:
    """Result of action execution."""

    action: str
    repos: list[tuple[str, str]]  # (owner, repo) tuples
    options: dict[str, Any]
    dry_run: bool = False


@dataclass
class ActionOptions:
    """Options for a specific action."""

    # Common options
    dry_run: bool = False

    # Describe options
    describe_model: str = DEFAULT_LLM_MODEL
    describe_force: bool = False

    # Tag options
    tag_model: str = DEFAULT_LLM_MODEL
    tag_force: bool = False
    tag_preferred: str = ""

    # Badges options
    badges_style: str = "flat-square"
    badges_apply: bool = False
    badges_max: int = 10

    # Health options
    health_rules: str = "default"

    # README options
    readme_model: str = DEFAULT_LLM_MODEL
    readme_force: bool = False
    readme_min_quality: float = 0.5

    # License options
    license_type: str = "mit"
    license_force: bool = False

    # Selected actions
    actions: list[str] = field(default_factory=list)


class ActionModal(ModalScreen[ActionResult | None]):
    """Modal screen for selecting and configuring actions."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+enter", "execute", "Execute"),
    ]

    def __init__(
        self,
        repos: list[tuple[str, str]],
        scope_description: str = "selected repositories",
    ) -> None:
        """Initialize action modal.

        Args:
            repos: List of (owner, repo) tuples to act on
            scope_description: Human-readable description of scope
        """
        super().__init__()
        self.repos = repos
        self.scope_description = scope_description
        self.options = ActionOptions()

    def compose(self) -> ComposeResult:
        """Compose the action modal."""
        yield Vertical(
            Static("Actions", classes="modal-title"),
            Static(
                f"Scope: [bold]{len(self.repos)}[/bold] {self.scope_description}",
                classes="modal-scope",
                markup=True,
            ),
            VerticalScroll(
                # Action selection
                Static(
                    "[bold]Select Actions[/bold]", classes="section-header", markup=True
                ),
                Checkbox("Generate Descriptions", id="action-describe"),
                Checkbox("Generate README", id="action-readme"),
                Checkbox("Add License", id="action-license"),
                Checkbox("Add Topics", id="action-tag"),
                Checkbox("Generate Badges", id="action-badges"),
                Checkbox("Health Check", id="action-health"),
                Checkbox("Audit", id="action-audit"),
                # Common options
                Static(
                    "[bold]Common Options[/bold]", classes="section-header", markup=True
                ),
                Checkbox("Dry Run (preview only)", id="opt-dry-run", value=True),
                # Describe options
                Static(
                    "[bold]Description Options[/bold]",
                    id="describe-section",
                    classes="section-header hidden",
                    markup=True,
                ),
                Horizontal(
                    Label("Model:", classes="field-label"),
                    RadioSet(
                        RadioButton("Haiku (fast)", id="model-haiku", value=True),
                        RadioButton("Sonnet (balanced)", id="model-sonnet"),
                        RadioButton("Opus (best)", id="model-opus"),
                        id="describe-model",
                        classes="model-select",
                    ),
                    classes="field-row",
                ),
                Checkbox(
                    "Force update existing",
                    id="describe-force",
                    classes="hidden-option",
                ),
                # Tag options
                Static(
                    "[bold]Topic Options[/bold]",
                    id="tag-section",
                    classes="section-header hidden",
                    markup=True,
                ),
                Horizontal(
                    Label("Model:", classes="field-label"),
                    RadioSet(
                        RadioButton("Haiku (fast)", id="tag-model-haiku", value=True),
                        RadioButton("Sonnet (balanced)", id="tag-model-sonnet"),
                        id="tag-model",
                        classes="model-select",
                    ),
                    classes="field-row",
                ),
                Horizontal(
                    Label("Preferred tags:", classes="field-label"),
                    Input(
                        placeholder="edtech: Educational, tool: CLI tools",
                        id="tag-preferred",
                    ),
                    classes="field-row",
                ),
                Checkbox(
                    "Force update existing", id="tag-force", classes="hidden-option"
                ),
                # Badges options
                Static(
                    "[bold]Badge Options[/bold]",
                    id="badges-section",
                    classes="section-header hidden",
                    markup=True,
                ),
                Horizontal(
                    Label("Style:", classes="field-label"),
                    RadioSet(
                        RadioButton("flat-square", id="style-flat-square", value=True),
                        RadioButton("flat", id="style-flat"),
                        RadioButton("for-the-badge", id="style-badge"),
                        id="badges-style",
                        classes="style-select",
                    ),
                    classes="field-row",
                ),
                Checkbox(
                    "Apply to README files", id="badges-apply", classes="hidden-option"
                ),
                # Health options
                Static(
                    "[bold]Health Check Options[/bold]",
                    id="health-section",
                    classes="section-header hidden",
                    markup=True,
                ),
                Horizontal(
                    Label("Rule set:", classes="field-label"),
                    RadioSet(
                        RadioButton("Default", id="rules-default", value=True),
                        RadioButton("Academic", id="rules-academic"),
                        RadioButton("Professional", id="rules-professional"),
                        id="health-rules",
                        classes="rules-select",
                    ),
                    classes="field-row",
                ),
                # README options
                Static(
                    "[bold]README Options[/bold]",
                    id="readme-section",
                    classes="section-header hidden",
                    markup=True,
                ),
                Horizontal(
                    Label("Model:", classes="field-label"),
                    RadioSet(
                        RadioButton(
                            "Haiku (fast)", id="readme-model-haiku", value=True
                        ),
                        RadioButton("Sonnet (balanced)", id="readme-model-sonnet"),
                        RadioButton("Opus (best)", id="readme-model-opus"),
                        id="readme-model",
                        classes="model-select",
                    ),
                    classes="field-row",
                ),
                Checkbox(
                    "Force update all READMEs",
                    id="readme-force",
                    classes="hidden-option",
                ),
                # License options
                Static(
                    "[bold]License Options[/bold]",
                    id="license-section",
                    classes="section-header hidden",
                    markup=True,
                ),
                Horizontal(
                    Label("License:", classes="field-label"),
                    RadioSet(
                        RadioButton("MIT", id="license-mit", value=True),
                        RadioButton("Apache 2.0", id="license-apache"),
                        RadioButton("GPL 3.0", id="license-gpl"),
                        RadioButton("BSD 3-Clause", id="license-bsd"),
                        id="license-type",
                        classes="style-select",
                    ),
                    classes="field-row",
                ),
                Checkbox(
                    "Replace existing licenses",
                    id="license-force",
                    classes="hidden-option",
                ),
                id="action-scroll",
                classes="action-form",
            ),
            Horizontal(
                Button("Cancel", variant="default", id="btn-cancel"),
                Button("Execute", variant="primary", id="btn-execute"),
                classes="modal-buttons",
            ),
            classes="action-modal",
        )

    def on_mount(self) -> None:
        """Focus the first checkbox on mount."""
        self.query_one("#action-describe", Checkbox).focus()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes to show/hide option sections."""
        checkbox_id = event.checkbox.id
        if checkbox_id is None:
            return

        # Map action checkboxes to their option sections
        section_map = {
            "action-describe": ["describe-section", "describe-force"],
            "action-readme": ["readme-section", "readme-force"],
            "action-license": ["license-section", "license-force"],
            "action-tag": ["tag-section", "tag-force"],
            "action-badges": ["badges-section", "badges-apply"],
            "action-health": ["health-section"],
        }

        if checkbox_id in section_map:
            for element_id in section_map[checkbox_id]:
                try:
                    element = self.query_one(f"#{element_id}")
                    if event.value:
                        element.remove_class("hidden")
                    else:
                        element.add_class("hidden")
                except Exception:
                    pass

        # Show model options for describe/tag together
        if checkbox_id in ("action-describe", "action-tag"):
            describe_checked = self.query_one("#action-describe", Checkbox).value
            tag_checked = self.query_one("#action-tag", Checkbox).value
            # Model options are shown if either is checked
            model_visible = describe_checked or tag_checked
            for element_id in ["describe-section"]:
                try:
                    element = self.query_one(f"#{element_id}")
                    if model_visible:
                        element.remove_class("hidden")
                    else:
                        element.add_class("hidden")
                except Exception:
                    pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-execute":
            self._execute_actions()

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)

    def action_execute(self) -> None:
        """Execute selected actions."""
        self._execute_actions()

    def _get_selected_actions(self) -> list[str]:
        """Get list of selected action names."""
        actions = []
        action_checkboxes = [
            ("action-describe", "describe"),
            ("action-readme", "readme"),
            ("action-license", "license"),
            ("action-tag", "tag"),
            ("action-badges", "badges"),
            ("action-health", "health"),
            ("action-audit", "audit"),
        ]
        for checkbox_id, action_name in action_checkboxes:
            try:
                checkbox = self.query_one(f"#{checkbox_id}", Checkbox)
                if checkbox.value:
                    actions.append(action_name)
            except Exception:
                pass
        return actions

    def _get_model_name(self, radio_set_id: str) -> str:
        """Get the selected model name from a radio set."""
        model_map = {
            "model-haiku": DEFAULT_LLM_MODEL,
            "tag-model-haiku": DEFAULT_LLM_MODEL,
            "readme-model-haiku": DEFAULT_LLM_MODEL,
            "model-sonnet": BALANCED_LLM_MODEL,
            "tag-model-sonnet": BALANCED_LLM_MODEL,
            "readme-model-sonnet": BALANCED_LLM_MODEL,
            "model-opus": ADVANCED_LLM_MODEL,
            "readme-model-opus": ADVANCED_LLM_MODEL,
        }
        try:
            radio_set = self.query_one(f"#{radio_set_id}", RadioSet)
            if radio_set.pressed_button:
                button_id = radio_set.pressed_button.id
                if button_id:
                    return model_map.get(button_id, DEFAULT_LLM_MODEL)
        except Exception:
            pass
        return DEFAULT_LLM_MODEL

    def _get_badge_style(self) -> str:
        """Get the selected badge style."""
        style_map = {
            "style-flat-square": "flat-square",
            "style-flat": "flat",
            "style-badge": "for-the-badge",
        }
        try:
            radio_set = self.query_one("#badges-style", RadioSet)
            if radio_set.pressed_button:
                button_id = radio_set.pressed_button.id
                if button_id:
                    return style_map.get(button_id, "flat-square")
        except Exception:
            pass
        return "flat-square"

    def _get_health_rules(self) -> str:
        """Get the selected health check rule set."""
        rules_map = {
            "rules-default": "default",
            "rules-academic": "academic",
            "rules-professional": "professional",
        }
        try:
            radio_set = self.query_one("#health-rules", RadioSet)
            if radio_set.pressed_button:
                button_id = radio_set.pressed_button.id
                if button_id:
                    return rules_map.get(button_id, "default")
        except Exception:
            pass
        return "default"

    def _get_license_type(self) -> str:
        """Get the selected license type."""
        license_map = {
            "license-mit": "mit",
            "license-apache": "apache-2.0",
            "license-gpl": "gpl-3.0",
            "license-bsd": "bsd-3-clause",
        }
        try:
            radio_set = self.query_one("#license-type", RadioSet)
            if radio_set.pressed_button:
                button_id = radio_set.pressed_button.id
                if button_id:
                    return license_map.get(button_id, "mit")
        except Exception:
            pass
        return "mit"

    def _execute_actions(self) -> None:
        """Gather options and execute selected actions."""
        actions = self._get_selected_actions()

        if not actions:
            self.app.notify("No actions selected", severity="warning", timeout=2)
            return

        # Gather options
        options: dict[str, Any] = {}

        # Common
        try:
            options["dry_run"] = self.query_one("#opt-dry-run", Checkbox).value
        except Exception:
            options["dry_run"] = True

        # Describe options
        if "describe" in actions:
            options["describe_model"] = self._get_model_name("describe-model")
            try:
                options["describe_force"] = self.query_one(
                    "#describe-force", Checkbox
                ).value
            except Exception:
                options["describe_force"] = False

        # Tag options
        if "tag" in actions:
            options["tag_model"] = self._get_model_name("tag-model")
            try:
                options["tag_force"] = self.query_one("#tag-force", Checkbox).value
            except Exception:
                options["tag_force"] = False
            try:
                options["tag_preferred"] = self.query_one("#tag-preferred", Input).value
            except Exception:
                options["tag_preferred"] = ""

        # Badges options
        if "badges" in actions:
            options["badges_style"] = self._get_badge_style()
            try:
                options["badges_apply"] = self.query_one(
                    "#badges-apply", Checkbox
                ).value
            except Exception:
                options["badges_apply"] = False

        # Health options
        if "health" in actions:
            options["health_rules"] = self._get_health_rules()

        # README options
        if "readme" in actions:
            options["readme_model"] = self._get_model_name("readme-model")
            try:
                options["readme_force"] = self.query_one(
                    "#readme-force", Checkbox
                ).value
            except Exception:
                options["readme_force"] = False

        # License options
        if "license" in actions:
            options["license_type"] = self._get_license_type()
            try:
                options["license_force"] = self.query_one(
                    "#license-force", Checkbox
                ).value
            except Exception:
                options["license_force"] = False

        # Create result with first action (we'll handle multiple actions in executor)
        result = ActionResult(
            action=",".join(actions),
            repos=self.repos,
            options=options,
            dry_run=options.get("dry_run", True),
        )

        self.dismiss(result)
