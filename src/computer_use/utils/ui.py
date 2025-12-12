"""
Enterprise-grade terminal UI with high-performance dashboard.
Single stable dashboard with bright colors and no flickering.
"""

import re
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE_PATTERN.sub("", text)


class VerbosityLevel(Enum):
    """Verbosity levels for UI output."""

    QUIET = 0
    NORMAL = 1
    VERBOSE = 2


class ActionType(Enum):
    """Types of actions for visual distinction."""

    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    OPEN = "open"
    READ = "read"
    SEARCH = "search"
    NAVIGATE = "navigate"
    ANALYZE = "analyze"
    EXECUTE = "execute"
    PLAN = "plan"
    COMPLETE = "complete"
    ERROR = "error"
    WEBHOOK = "webhook"


ACTION_ICONS = {
    ActionType.CLICK: "●",
    ActionType.TYPE: "⌨",
    ActionType.SCROLL: "↕",
    ActionType.OPEN: "◈",
    ActionType.READ: "◉",
    ActionType.SEARCH: "⊙",
    ActionType.NAVIGATE: "→",
    ActionType.ANALYZE: "◐",
    ActionType.EXECUTE: "▸",
    ActionType.PLAN: "◇",
    ActionType.COMPLETE: "✓",
    ActionType.ERROR: "✗",
    ActionType.WEBHOOK: "⚡",
}


HIGH_SIGNAL_NAVIGATE_KEYWORDS = (
    "step",
    "navigat",
    "login",
    "click",
    "success",
    "fail",
)

HIGH_SIGNAL_CLICK_KEYWORDS = (
    "button",
    "link",
    "submit",
    "login",
    "sign",
)

THEME = {
    "bg": "#0d1117",
    "fg": "#e6edf3",
    "primary": "#58a6ff",
    "secondary": "#a371f7",
    "accent": "#00ffff",
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    "muted": "#7d8590",
    "surface": "#161b22",
    "border": "#30363d",
    "bright": "#ffffff",
}


@dataclass
class ActionLogEntry:
    """Single entry in the action log with optional nested result."""

    action_type: ActionType
    message: str
    target: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"
    result: Optional[str] = None


@dataclass
class WebhookEvent:
    """Webhook/server event entry."""

    event_type: str
    source: str
    message: str
    timestamp: float = field(default_factory=time.time)


class DashboardManager:
    """
    High-performance singleton dashboard manager.
    Single stable dashboard with no flickering.
    """

    _instance: Optional["DashboardManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DashboardManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self.console = Console(force_terminal=True)
        self.verbosity = VerbosityLevel.NORMAL
        self._live: Optional[Live] = None
        self._lock = threading.Lock()

        self._task: Optional[str] = None
        self._current_agent: Optional[str] = None
        self._current_action: Optional[str] = None
        self._action_target: Optional[str] = None
        self._step_current = 0
        self._step_total = 0
        self._status = "ready"

        self._action_log: List[ActionLogEntry] = []
        self._max_log_entries = 100

        self._webhook_events: List[WebhookEvent] = []
        self._max_webhook_events = 4

        self._is_running = False
        self._anim_frame = 0
        self._last_refresh = 0.0

        self._human_assistance_active = False
        self._human_assistance_reason: Optional[str] = None
        self._human_assistance_instructions: Optional[str] = None

        self._browser_profile: Optional[str] = None
        self._browser_session_active = False

    @property
    def is_quiet(self) -> bool:
        """Return True when verbosity is QUIET."""
        return self.verbosity == VerbosityLevel.QUIET

    @property
    def is_verbose(self) -> bool:
        """Return True when verbosity is VERBOSE."""
        return self.verbosity == VerbosityLevel.VERBOSE

    def set_verbosity(self, level: VerbosityLevel) -> None:
        """Set the verbosity level."""
        self.verbosity = level

    @staticmethod
    def _trim_tail(entries: List, max_entries: int) -> List:
        """Trim a list to its last max_entries when it grows too large."""
        if len(entries) > max_entries * 2:
            return entries[-max_entries:]
        return entries

    def _is_raw_tool_call(self, message: str) -> bool:
        """Check if message is a raw tool call that should be filtered."""
        if '{"' in message and '":' in message:
            return True
        if message.count(":") == 1 and message.endswith("}"):
            return True
        return False

    def _is_duplicate_entry(self, entry: ActionLogEntry, idx: int) -> bool:
        """Check if entry is a duplicate of a nearby entry."""
        if idx == 0:
            return False

        for i in range(max(0, idx - 3), idx):
            prev = self._action_log[i]
            if prev.message == entry.message:
                return True
            if entry.message.startswith(
                prev.message.rstrip("...")
            ) or prev.message.startswith(entry.message.rstrip("...")):
                if entry.status == "complete" and prev.status != "complete":
                    return False
                return True
        return False

    def _is_high_signal_entry(self, entry: ActionLogEntry, idx: int = 0) -> bool:
        """Determine if a log entry is high-signal for normal verbosity mode."""
        if self._is_raw_tool_call(entry.message):
            return False

        if self._is_duplicate_entry(entry, idx):
            return False

        high_signal_types = {
            ActionType.COMPLETE,
            ActionType.ERROR,
            ActionType.PLAN,
            ActionType.OPEN,
            ActionType.WEBHOOK,
        }

        if entry.action_type in high_signal_types:
            return True

        if entry.status in {"error", "complete"}:
            return True

        if entry.action_type == ActionType.NAVIGATE:
            msg_lower = entry.message.lower()
            return any(kw in msg_lower for kw in HIGH_SIGNAL_NAVIGATE_KEYWORDS)

        if entry.action_type == ActionType.CLICK:
            msg_lower = entry.message.lower()
            return any(kw in msg_lower for kw in HIGH_SIGNAL_CLICK_KEYWORDS)

        return False

    def _get_filtered_entries(self) -> List[ActionLogEntry]:
        """Get log entries filtered by verbosity level."""
        if self.is_verbose:
            return [
                e
                for i, e in enumerate(self._action_log)
                if not self._is_raw_tool_call(e.message)
            ]

        if self.is_quiet:
            return [e for e in self._action_log if e.status in ("complete", "error")]

        return [
            e
            for i, e in enumerate(self._action_log)
            if self._is_high_signal_entry(e, i)
        ]

    def _build_header(self) -> Panel:
        """Build the compact header section with title and task."""
        title = Text()
        title.append(" ◆ ", style=f"bold {THEME['accent']}")
        title.append("COMPUTER USE AGENT", style=f"bold {THEME['bright']}")

        if self._task:
            title.append("  │  ", style=THEME["border"])
            task_display = (
                self._task[:60] + "..." if len(self._task) > 60 else self._task
            )
            title.append(task_display, style=THEME["fg"])

        return Panel(
            title,
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_human_assistance_panel(self) -> Panel:
        """Render the human assistance block."""
        lines: List[Text] = []

        ha_header = Text()
        ha_header.append(" 🤝 ", style=f"bold {THEME['warning']}")
        ha_header.append("HUMAN ASSISTANCE REQUIRED", style=f"bold {THEME['bright']}")
        lines.append(ha_header)
        lines.append(Text(""))

        if self._human_assistance_reason:
            lines.append(Text(" Reason:", style=f"bold {THEME['muted']}"))
            lines.append(Text(f" {self._human_assistance_reason}", style=THEME["fg"]))
            lines.append(Text(""))

        if self._human_assistance_instructions:
            lines.append(Text(" Instructions:", style=f"bold {THEME['muted']}"))
            lines.append(
                Text(f" {self._human_assistance_instructions}", style=THEME["fg"])
            )
            lines.append(Text(""))

        lines.append(Text(" Browser window remains open.", style=THEME["muted"]))
        lines.append(Text(""))

        buttons = Text()
        buttons.append(" ")
        buttons.append("[P]", style=f"bold {THEME['success']}")
        buttons.append(" Proceed  ", style=THEME["fg"])
        buttons.append("[R]", style=f"bold {THEME['primary']}")
        buttons.append(" Retry  ", style=THEME["fg"])
        buttons.append("[S]", style=f"bold {THEME['warning']}")
        buttons.append(" Skip  ", style=THEME["fg"])
        buttons.append("[C]", style=f"bold {THEME['error']}")
        buttons.append(" Cancel", style=THEME["fg"])
        lines.append(buttons)

        return Panel(
            Group(*lines),
            title=f"[{THEME['warning']}]ACTION REQUIRED[/]",
            box=box.ROUNDED,
            border_style=THEME["warning"],
            padding=(0, 1),
        )

    def _build_activity(self) -> Panel:
        """Build the activity log section with hierarchical entries."""
        lines = []

        if self._human_assistance_active:
            return self._build_human_assistance_panel()

        filtered_entries = self._get_filtered_entries()

        if filtered_entries:
            for entry in filtered_entries:
                icon = ACTION_ICONS.get(entry.action_type, "○")

                if entry.status == "complete":
                    icon_style = THEME["success"]
                    msg_style = THEME["fg"]
                elif entry.status == "error":
                    icon_style = THEME["error"]
                    msg_style = THEME["error"]
                else:
                    icon_style = THEME["accent"]
                    msg_style = THEME["fg"]

                log_line = Text()
                log_line.append(f"  {icon} ", style=icon_style)
                log_line.append(entry.message, style=msg_style)
                lines.append(log_line)

                if entry.result:
                    result_line = Text()
                    result_line.append("    └─ ", style=THEME["muted"])
                    result_line.append(entry.result, style=THEME["secondary"])
                    lines.append(result_line)
        else:
            lines.append(Text("  Waiting for activity...", style=THEME["muted"]))

        if self._current_action:
            lines.append(Text(""))

            spinner_text = Text()
            spinner_text.append(self._current_action, style=f"bold {THEME['bright']}")
            if self._action_target:
                spinner_text.append(f" {self._action_target}", style=THEME["warning"])

            spinner = Spinner("dots", text=spinner_text, style=THEME["accent"])
            lines.append(spinner)

        if self._webhook_events:
            lines.append(Text(""))
            for event in self._webhook_events[-self._max_webhook_events :]:
                event_line = Text()
                event_line.append("  ⚡ ", style=THEME["warning"])
                event_line.append(f"{event.source}: ", style=THEME["accent"])
                event_line.append(event.message, style=THEME["fg"])
                lines.append(event_line)

        return Panel(
            Group(*lines),
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_status_bar(self) -> Panel:
        """Build the bottom status bar with key info."""
        status = Text()

        if self._current_agent:
            status.append(" ", style="")
            status.append("●", style=f"bold {THEME['success']}")
            status.append(f" {self._current_agent}", style=f"bold {THEME['accent']}")
        else:
            status.append(" ○ Ready", style=THEME["muted"])

        status.append("  │  ", style=THEME["border"])

        if self._step_total > 0:
            status.append(
                f"Step {self._step_current}/{self._step_total}", style=THEME["fg"]
            )
        else:
            status.append("Idle", style=THEME["muted"])

        status.append("  │  ", style=THEME["border"])

        if self._browser_session_active:
            status.append("●", style=f"bold {THEME['success']}")
            profile = self._browser_profile or "Browser"
            status.append(f" {profile}", style=THEME["fg"])
        else:
            status.append("○", style=THEME["muted"])
            status.append(" Browser", style=THEME["muted"])

        status.append("  │  ", style=THEME["border"])

        status.append("ESC", style=f"bold {THEME['muted']}")
        status.append(" cancel  ", style=THEME["muted"])
        status.append("Ctrl+C", style=f"bold {THEME['muted']}")
        status.append(" quit", style=THEME["muted"])

        return Panel(
            status,
            box=box.ROUNDED,
            border_style=THEME["accent"],
            padding=(0, 0),
        )

    def _build_dashboard(self) -> Layout:
        """Build the full-screen dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="activity", ratio=1),
            Layout(name="status_bar", size=3),
        )

        layout["header"].update(self._build_header())
        layout["activity"].update(self._build_activity())
        layout["status_bar"].update(self._build_status_bar())

        return layout

    def start_dashboard(self) -> None:
        """Start the live full-screen dashboard display."""
        if self.is_quiet:
            return

        if self._is_running:
            return

        self._is_running = True
        self._live = Live(
            self._build_dashboard(),
            console=self.console,
            refresh_per_second=4,
            screen=True,
            transient=False,
        )
        self._live.start()

    def stop_dashboard(self, print_log: bool = True) -> None:
        """Stop the live dashboard display and optionally print session log."""
        if not self._is_running:
            return

        self._is_running = False
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

        if print_log and self._action_log:
            self.print_session_log()

    def refresh(self) -> None:
        """Update the dashboard content with throttling."""
        if not self._is_running or not self._live:
            return

        now = time.time()
        if now - self._last_refresh < 0.2:
            return
        self._last_refresh = now

        with self._lock:
            try:
                self._live.update(self._build_dashboard())
            except Exception:
                pass

    def set_task(self, task: str) -> None:
        """Set the current task being executed."""
        self._task = task
        self._status = "working"
        self._action_log = []
        self.refresh()

    def set_agent(self, agent_name: str) -> None:
        """Set the current active agent."""
        self._current_agent = agent_name
        self.refresh()

    def set_action(
        self,
        action: str,
        target: Optional[str] = None,
    ) -> None:
        """Set the current action being performed."""
        self._current_action = strip_ansi(action)
        self._action_target = strip_ansi(target) if target else None
        self.refresh()

    def clear_action(self) -> None:
        """Clear the current action."""
        self._current_action = None
        self._action_target = None
        self.refresh()

    def set_last_result(self, result: str) -> None:
        """Set the result on the most recent log entry for hierarchical display."""
        if self._action_log:
            self._action_log[-1].result = strip_ansi(result)
            self.refresh()

    def set_steps(self, current: int, total: int) -> None:
        """Set the step progress."""
        self._step_current = current
        self._step_total = total
        self.refresh()

    def add_log_entry(
        self,
        action_type: ActionType,
        message: str,
        target: Optional[str] = None,
        status: str = "pending",
    ) -> int:
        """Add an entry to the action log."""
        clean_message = strip_ansi(message)
        clean_target = strip_ansi(target) if target else None

        entry = ActionLogEntry(
            action_type=action_type,
            message=clean_message,
            target=clean_target,
            status=status,
        )
        self._action_log.append(entry)
        self._action_log = self._trim_tail(self._action_log, self._max_log_entries)

        self.refresh()
        return len(self._action_log) - 1

    def update_log_entry(self, idx: int, status: str) -> None:
        """Update the status of a log entry."""
        if 0 <= idx < len(self._action_log):
            self._action_log[idx].status = status
            self.refresh()

    def add_webhook_event(self, event_type: str, source: str, message: str) -> None:
        """Add a webhook/server event."""
        event = WebhookEvent(
            event_type=event_type,
            source=source,
            message=message,
        )
        self._webhook_events.append(event)
        self._webhook_events = self._trim_tail(
            self._webhook_events, self._max_webhook_events
        )

        self.refresh()

    def complete_task(self, success: bool = True) -> None:
        """Mark the current task as complete."""
        self._status = "complete" if success else "error"
        self._current_action = None
        self._action_target = None

        status_type = ActionType.COMPLETE if success else ActionType.ERROR
        status_msg = "Task completed successfully" if success else "Task failed"
        self.add_log_entry(
            status_type, status_msg, status="complete" if success else "error"
        )
        self.refresh()

    def print_session_log(self) -> None:
        """Print the complete session log to console (scrollable output)."""
        self.console.print()

        self.console.print(
            f"  [{THEME['accent']}]◆[/] [{THEME['bright']}]Session Log[/]"
        )
        self.console.print(f"  [{THEME['muted']}]{'─' * 50}[/]")

        if self._task:
            self.console.print(f"  [{THEME['muted']}]Task:[/] {self._task}")
            self.console.print()

        filtered = self._get_filtered_entries()
        for entry in filtered:
            icon = ACTION_ICONS.get(entry.action_type, "○")

            if entry.status == "complete":
                icon_style = THEME["success"]
                msg_style = THEME["fg"]
            elif entry.status == "error":
                icon_style = THEME["error"]
                msg_style = THEME["error"]
            else:
                icon_style = THEME["accent"]
                msg_style = THEME["fg"]

            self.console.print(
                f"  [{icon_style}]{icon}[/] [{msg_style}]{entry.message}[/]"
            )

            if entry.result:
                self.console.print(
                    f"    [{THEME['muted']}]└─[/] [{THEME['secondary']}]{entry.result}[/]"
                )

        self.console.print(f"  [{THEME['muted']}]{'─' * 50}[/]")
        self.console.print()

    def show_human_assistance(self, reason: str, instructions: str) -> None:
        """Show human assistance panel in the dashboard."""
        self._human_assistance_active = True
        self._human_assistance_reason = reason
        self._human_assistance_instructions = instructions
        self.refresh()

    def hide_human_assistance(self) -> None:
        """Hide the human assistance panel."""
        self._human_assistance_active = False
        self._human_assistance_reason = None
        self._human_assistance_instructions = None
        self.refresh()

    def set_browser_session(self, active: bool, profile: Optional[str] = None) -> None:
        """Set browser session state for status bar display."""
        self._browser_session_active = active
        self._browser_profile = profile
        self.refresh()


dashboard = DashboardManager()
console = dashboard.console


_key_bindings = KeyBindings()
_voice_mode_enabled = {"value": False}


@_key_bindings.add("enter")
def _on_enter(event):
    """Handle Enter key - submit the input."""
    event.current_buffer.validate_and_handle()


@_key_bindings.add("c-j")
def _on_ctrl_j(event):
    """Handle Ctrl+J - insert newline."""
    event.current_buffer.insert_text("\n")


@_key_bindings.add("escape", "enter")
def _on_alt_enter(event):
    """Handle Alt/Option+Enter - insert newline."""
    event.current_buffer.insert_text("\n")


@_key_bindings.add("f5")
def _on_f5(event):
    """Handle F5 - toggle voice input mode."""
    _voice_mode_enabled["value"] = not _voice_mode_enabled["value"]
    mode = "Voice" if _voice_mode_enabled["value"] else "Text"
    print_info(f"Switched to {mode} mode")


_prompt_session = PromptSession(
    history=None,
    multiline=True,
    key_bindings=_key_bindings,
)


def _log_or_print(
    action_type: ActionType,
    message: str,
    *,
    status: str,
    style_key: str,
    symbol: str,
    respect_quiet: bool,
) -> None:
    """Log to dashboard when running, otherwise print to console."""
    if respect_quiet and dashboard.is_quiet:
        return

    if dashboard._is_running:
        dashboard.add_log_entry(action_type, message, status=status)
        return

    console.print(f"  [{THEME[style_key]}]{symbol}[/] {message}")


def print_banner() -> None:
    """Display startup banner."""
    if dashboard.is_quiet:
        return

    console.print()
    console.print(
        f"  [bold {THEME['accent']}]◆[/] [bold {THEME['bright']}]Computer Use Agent[/]"
    )
    console.print(f"    [{THEME['muted']}]Autonomous Desktop & Web Automation[/]")
    console.print()


@contextmanager
def startup_spinner(message: str):
    """Context manager for startup tasks with spinner."""
    if dashboard.is_quiet:
        yield
        return

    status_text = Text()
    status_text.append("  ◌ ", style=f"bold {THEME['accent']}")
    status_text.append(message, style=THEME["muted"])

    spinner = Spinner("dots", text=status_text, style=THEME["accent"])

    try:
        with Live(spinner, console=console, refresh_per_second=10, transient=True):
            yield
    except Exception:
        raise


def print_startup_step(message: str, success: bool = True) -> None:
    """Print a startup step result."""
    if dashboard.is_quiet:
        return

    if success:
        console.print(f"  [{THEME['success']}]✓[/] [{THEME['fg']}]{message}[/]")
    else:
        console.print(f"  [{THEME['error']}]✗[/] [{THEME['fg']}]{message}[/]")


def print_section_header(title: str, icon: str = "") -> None:
    """Print styled section header."""
    if dashboard.is_quiet:
        return

    if dashboard.is_verbose:
        console.print()
        text = Text()
        if icon:
            text.append(f"{icon} ", style=THEME["secondary"])
        text.append(title, style=f"bold {THEME['primary']}")
        console.print(text)
        console.print("─" * 50, style=THEME["border"])


def print_platform_info(capabilities) -> None:
    """Display platform capabilities in compact format."""
    if dashboard.is_quiet:
        return

    if dashboard.is_verbose:
        console.print()
        main_table = Table(
            box=box.ROUNDED,
            show_header=False,
            padding=(0, 1),
            collapse_padding=True,
            border_style=THEME["border"],
        )
        main_table.add_column("", style=f"bold {THEME['muted']}")
        main_table.add_column("", style=THEME["fg"])

        main_table.add_row(
            "Platform",
            f"{capabilities.os_type.title()} {capabilities.os_version}",
        )
        main_table.add_row(
            "Display",
            f"{capabilities.screen_resolution[0]}×{capabilities.screen_resolution[1]} @ {capabilities.scaling_factor}x",
        )

        if capabilities.gpu_available:
            main_table.add_row(
                "GPU", f"[{THEME['success']}]✓ {capabilities.gpu_type}[/]"
            )
        else:
            main_table.add_row("GPU", f"[{THEME['warning']}]CPU mode[/]")

        if capabilities.accessibility_api_available:
            main_table.add_row(
                "Accessibility",
                f"[{THEME['success']}]✓ {capabilities.accessibility_api_type}[/]",
            )
        else:
            main_table.add_row("Accessibility", f"[{THEME['warning']}]Not available[/]")

        panel = Panel(
            Align.left(main_table),
            title=f"[{THEME['primary']}]Platform[/]",
            border_style=THEME["border"],
            padding=(0, 1),
        )
        console.print(panel)
        console.print()
    else:
        platform_str = f"{capabilities.os_type.title()} {capabilities.os_version}"
        display_str = (
            f"{capabilities.screen_resolution[0]}×{capabilities.screen_resolution[1]}"
        )
        gpu_str = (
            f"[{THEME['success']}]GPU[/]"
            if capabilities.gpu_available
            else f"[{THEME['muted']}]CPU[/]"
        )
        acc_str = (
            f"[{THEME['success']}]✓[/]"
            if capabilities.accessibility_api_available
            else f"[{THEME['warning']}]![/]"
        )

        console.print(
            f"  [{THEME['muted']}]Platform[/] [{THEME['fg']}]{platform_str}[/]  "
            f"[{THEME['muted']}]Display[/] [{THEME['fg']}]{display_str}[/]  "
            f"{gpu_str}  [{THEME['muted']}]Accessibility[/] {acc_str}"
        )


def print_status_overview(title: str, items: dict) -> None:
    """Render a concise key-value overview."""
    if dashboard.is_quiet:
        return

    if not items:
        return

    if dashboard.is_verbose:
        table = Table(
            box=box.MINIMAL_DOUBLE_HEAD,
            show_header=False,
            padding=(0, 1),
            collapse_padding=True,
        )
        table.add_column("", style=f"bold {THEME['muted']}")
        table.add_column("", style=THEME["fg"])

        for label, value in items.items():
            table.add_row(label, str(value))

        panel = Panel(
            Align.left(table),
            title=f"[{THEME['primary']}]{title}[/]",
            border_style=THEME["border"],
            padding=(0, 1),
        )
        console.print(panel)
        console.print()
    else:
        parts = []
        for label, value in list(items.items())[:4]:
            parts.append(f"[{THEME['muted']}]{label}[/] [{THEME['fg']}]{value}[/]")
        console.print(f"  {' · '.join(parts)}")


def print_ready() -> None:
    """Print ready message with keyboard hints."""
    if dashboard.is_quiet:
        return

    console.print()
    console.print(
        f"  [{THEME['success']}]●[/] [{THEME['bright']}]Ready[/]  "
        f"[{THEME['muted']}]F5[/] voice  "
        f"[{THEME['muted']}]ESC[/] cancel  "
        f"[{THEME['muted']}]Ctrl+C[/] quit"
    )
    console.print()


def print_verbose_only(message: str) -> None:
    """Print message only in verbose mode."""
    if dashboard.is_verbose:
        console.print(f"  {message}")


def print_step(step: int, action: str, target: str, reasoning: str) -> None:
    """Display agent step with clean formatting."""
    if dashboard.is_verbose:
        text = Text()
        text.append(f"  {step}. ", style=THEME["muted"])
        text.append(action, style=f"bold {THEME['accent']}")
        text.append(" → ", style=THEME["muted"])
        text.append(target, style=THEME["fg"])
        console.print(text)


def print_info(message: str) -> None:
    """Print an info message."""
    _log_or_print(
        ActionType.ANALYZE,
        message,
        status="pending",
        style_key="accent",
        symbol="ℹ",
        respect_quiet=True,
    )


def print_success(message: str) -> None:
    """Print a success message."""
    _log_or_print(
        ActionType.COMPLETE,
        message,
        status="complete",
        style_key="success",
        symbol="✓",
        respect_quiet=True,
    )


def print_warning(message: str) -> None:
    """Print a warning message."""
    _log_or_print(
        ActionType.ERROR,
        message,
        status="pending",
        style_key="warning",
        symbol="⚠",
        respect_quiet=False,
    )


def print_failure(message: str) -> None:
    """Print a failure message."""
    _log_or_print(
        ActionType.ERROR,
        message,
        status="error",
        style_key="error",
        symbol="✗",
        respect_quiet=False,
    )


def print_action_result(success: bool, message: str) -> None:
    """Print the result of an action."""
    if dashboard.is_quiet:
        return

    if success:
        print_success(message)
    else:
        print_failure(message)


@contextmanager
def action_spinner(action: str, target: str = ""):
    """Context manager for actions with status."""
    if dashboard.is_quiet:
        yield
        return

    display = f"{action} {target}".strip()
    idx = dashboard.add_log_entry(ActionType.EXECUTE, display)
    dashboard.set_action(action, target if target else None)

    try:
        yield
        dashboard.update_log_entry(idx, "complete")
    except Exception:
        dashboard.update_log_entry(idx, "error")
        raise
    finally:
        dashboard.clear_action()


def print_task_result(result) -> None:
    """Display the final task result."""
    if dashboard.is_quiet:
        return

    console.print()

    success = (hasattr(result, "overall_success") and result.overall_success) or (
        hasattr(result, "task_completed") and result.task_completed
    )

    if success:
        console.print(f"[bold {THEME['success']}]✓ Complete[/]")
        console.print()

        if hasattr(result, "result") and result.result:
            wrapped = (
                result.result[:200] + "..."
                if len(result.result) > 200
                else result.result
            )
            console.print(f"  [{THEME['fg']}]{wrapped}[/]")

        if hasattr(result, "final_value") and result.final_value:
            console.print(f"  [{THEME['accent']}]Result: {result.final_value}[/]")
    else:
        console.print(f"[bold {THEME['error']}]✗ Failed[/]")

        if hasattr(result, "error") and result.error:
            console.print(f"  [{THEME['error']}]{result.error}[/]")

    console.print()


async def get_task_input(start_with_voice: bool = False) -> Optional[str]:
    """Get task input from user."""
    import asyncio

    try:
        console.print(f"[{THEME['accent']}]What would you like me to do?[/]")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _prompt_session.prompt(
                FormattedText([(THEME["accent"], "❯ ")]),
                multiline=True,
            ),
        )
        return result.strip() if result else None

    except (EOFError, KeyboardInterrupt):
        return None


def format_duration(seconds: float) -> str:
    """Format duration for display."""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"


class HumanAssistanceResult(Enum):
    """Result of human assistance prompt."""

    PROCEED = "proceed"
    RETRY = "retry"
    SKIP = "skip"
    CANCEL = "cancel"


def _resolve_human_choice(choice: str) -> Optional[HumanAssistanceResult]:
    """Map raw input to a HumanAssistanceResult or None if unknown."""
    normalized = choice.strip().lower()

    if normalized in ("", "p", "proceed"):
        return HumanAssistanceResult.PROCEED
    if normalized in ("r", "retry"):
        return HumanAssistanceResult.RETRY
    if normalized in ("s", "skip"):
        return HumanAssistanceResult.SKIP
    if normalized in ("c", "cancel", "q", "quit"):
        return HumanAssistanceResult.CANCEL

    return None


def _log_human_assistance_result(result: HumanAssistanceResult) -> None:
    """Log the outcome of the human assistance prompt."""
    if result is HumanAssistanceResult.PROCEED:
        dashboard.add_log_entry(
            ActionType.COMPLETE,
            "Human assistance: Proceeding",
            status="complete",
        )
    elif result is HumanAssistanceResult.RETRY:
        dashboard.add_log_entry(ActionType.EXECUTE, "Human assistance: Retrying")
    elif result is HumanAssistanceResult.SKIP:
        dashboard.add_log_entry(ActionType.NAVIGATE, "Human assistance: Skipped")
    elif result is HumanAssistanceResult.CANCEL:
        dashboard.add_log_entry(
            ActionType.ERROR, "Human assistance: Cancelled", status="error"
        )


def _finish_human_assistance(result: HumanAssistanceResult) -> HumanAssistanceResult:
    """Hide the panel and log the human assistance outcome."""
    _log_human_assistance_result(result)
    dashboard.hide_human_assistance()
    return result


def prompt_human_assistance(reason: str, instructions: str) -> HumanAssistanceResult:
    """
    Display a styled human assistance dialog integrated in the dashboard.

    Args:
        reason: Why human help is needed
        instructions: What the human needs to do

    Returns:
        HumanAssistanceResult indicating user's choice
    """
    dashboard.show_human_assistance(reason, instructions)

    while True:
        try:
            choice = console.input(f"\n  [{THEME['accent']}]Select action ›[/] ")
            resolved = _resolve_human_choice(choice)
            if resolved:
                return _finish_human_assistance(resolved)

        except (EOFError, KeyboardInterrupt):
            return _finish_human_assistance(HumanAssistanceResult.CANCEL)
