"""
Enterprise-grade terminal UI with dashboard layout.
Features shimmer effects, animated progress, and live status updates.
"""

import asyncio
import os
import sys
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
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text


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
}


THEME = {
    "bg": "#1a1b26",
    "fg": "#c0caf5",
    "primary": "#7aa2f7",
    "secondary": "#bb9af7",
    "accent": "#7dcfff",
    "success": "#9ece6a",
    "warning": "#e0af68",
    "error": "#f7768e",
    "muted": "#565f89",
    "surface": "#24283b",
    "border": "#414868",
}


@dataclass
class ActionLogEntry:
    """Single entry in the action log."""

    action_type: ActionType
    message: str
    target: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"
    detail: Optional[str] = None


class ShimmerText:
    """
    Renderable that creates a shimmer effect on text.
    The shimmer moves across the text creating a loading animation.
    """

    def __init__(
        self,
        text: str,
        style: str = "bold",
        shimmer_style: str = "bold white",
        width: int = 3,
    ):
        self.text = text
        self.style = style
        self.shimmer_style = shimmer_style
        self.width = width
        self._position = 0
        self._direction = 1

    def __rich__(self) -> Text:
        """Render the shimmer text."""
        result = Text()
        text_len = len(self.text)

        for i, char in enumerate(self.text):
            distance = abs(i - self._position)
            if distance < self.width:
                intensity = 1.0 - (distance / self.width)
                if intensity > 0.7:
                    result.append(char, style=self.shimmer_style)
                elif intensity > 0.3:
                    result.append(char, style=f"{self.style} dim")
                else:
                    result.append(char, style=self.style)
            else:
                result.append(char, style=self.style)

        self._position += self._direction
        if self._position >= text_len + self.width:
            self._position = -self.width
        elif self._position < -self.width:
            self._position = text_len + self.width

        return result


class AnimatedProgress:
    """
    Animated progress bar with smooth fill animation.
    """

    def __init__(self, total: int = 100, width: int = 20):
        self.total = total
        self.width = width
        self._current = 0.0
        self._target = 0.0
        self._fill_char = "█"
        self._empty_char = "░"

    def set_progress(self, value: float) -> None:
        """Set target progress value (0-100)."""
        self._target = min(max(value, 0), 100)

    def __rich__(self) -> Text:
        """Render the progress bar with smooth animation."""
        if self._current < self._target:
            self._current = min(self._current + 2, self._target)
        elif self._current > self._target:
            self._current = max(self._current - 2, self._target)

        filled = int((self._current / 100) * self.width)
        empty = self.width - filled

        bar = Text()
        bar.append(self._fill_char * filled, style=f"bold {THEME['success']}")
        bar.append(self._empty_char * empty, style=THEME["muted"])

        return bar


class DashboardManager:
    """
    Singleton manager for the enterprise dashboard UI.
    Handles all terminal output with live updates and animations.
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

        self.console = Console()
        self.verbosity = VerbosityLevel.NORMAL
        self._live: Optional[Live] = None
        self._update_lock = threading.Lock()

        self._task: Optional[str] = None
        self._current_agent: Optional[str] = None
        self._current_action: Optional[str] = None
        self._action_target: Optional[str] = None
        self._step_current = 0
        self._step_total = 0
        self._status = "ready"

        self._action_log: List[ActionLogEntry] = []
        self._max_log_entries = 6

        self._shimmer = ShimmerText("Initializing...", style=THEME["accent"])
        self._progress = AnimatedProgress()
        self._is_running = False

        self._last_refresh = 0.0
        self._min_refresh_interval = 0.1
        self._pending_refresh = False
        self._layout: Optional[Layout] = None

    def set_verbosity(self, level: VerbosityLevel) -> None:
        """Set the verbosity level."""
        self.verbosity = level

    def _build_header(self) -> Panel:
        """Build the header bar with app name and status."""
        header_text = Text()
        header_text.append("  COMPUTER USE AGENT", style=f"bold {THEME['primary']}")

        status_style = THEME["success"] if self._status == "ready" else THEME["accent"]
        status_text = f"[{self._status}]"

        right_text = Text(status_text, style=f"bold {status_style}")

        table = Table.grid(expand=True)
        table.add_column(justify="left", ratio=1)
        table.add_column(justify="right")
        table.add_row(header_text, right_text)

        return Panel(
            table,
            box=box.HEAVY_HEAD,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_task_panel(self) -> Panel:
        """Build the current task display panel."""
        if self._task:
            task_text = Text()
            task_text.append("Task: ", style=f"bold {THEME['muted']}")
            display_task = (
                self._task[:70] + "..." if len(self._task) > 70 else self._task
            )
            task_text.append(display_task, style=THEME["fg"])
        else:
            task_text = Text("Awaiting task...", style=THEME["muted"])

        return Panel(
            task_text,
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_action_panel(self) -> Panel:
        """Build the current action panel with shimmer effect."""
        if self._current_action:
            action_content = Table.grid(expand=True)
            action_content.add_column(justify="left", ratio=1)
            action_content.add_column(justify="right", width=25)

            action_text = Text()
            action_text.append("▸ ", style=f"bold {THEME['accent']}")

            if self._is_running:
                shimmer = ShimmerText(
                    self._current_action, style=THEME["accent"], width=4
                )
                action_text.append_text(shimmer.__rich__())
            else:
                action_text.append(self._current_action, style=THEME["accent"])

            if self._action_target:
                action_text.append(f" '{self._action_target}'", style=THEME["warning"])

            action_content.add_row(action_text, self._progress)
        else:
            action_content = Text("  Idle", style=THEME["muted"])

        return Panel(
            action_content,
            title=f"[{THEME['muted']}]Current Action[/]",
            title_align="left",
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_log_panel(self) -> Panel:
        """Build the action log panel with status icons."""
        log_content = Table.grid(expand=True)
        log_content.add_column(width=3)
        log_content.add_column(ratio=1)

        recent_entries = self._action_log[-self._max_log_entries :]

        for entry in recent_entries:
            icon = ACTION_ICONS.get(entry.action_type, "○")

            if entry.status == "complete":
                icon_style = THEME["success"]
                msg_style = THEME["muted"]
            elif entry.status == "error":
                icon_style = THEME["error"]
                msg_style = THEME["error"]
            elif entry.status == "pending":
                icon_style = THEME["accent"]
                msg_style = THEME["fg"]
            else:
                icon_style = THEME["muted"]
                msg_style = THEME["muted"]

            icon_text = Text(f" {icon} ", style=icon_style)

            msg_text = Text()
            display_msg = (
                entry.message[:60] + "..." if len(entry.message) > 60 else entry.message
            )
            msg_text.append(display_msg, style=msg_style)

            if entry.target:
                target_display = (
                    entry.target[:20] + "..."
                    if len(entry.target) > 20
                    else entry.target
                )
                msg_text.append(f" → {target_display}", style=THEME["muted"])

            log_content.add_row(icon_text, msg_text)

        if not recent_entries:
            log_content.add_row(
                Text(" ○ ", style=THEME["muted"]),
                Text("No actions yet", style=THEME["muted"]),
            )

        return Panel(
            log_content,
            title=f"[{THEME['muted']}]Action Log[/]",
            title_align="left",
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_status_bar(self) -> Panel:
        """Build the persistent status bar at the bottom."""
        status_table = Table.grid(expand=True)
        status_table.add_column(justify="left", width=20)
        status_table.add_column(justify="center", ratio=1)
        status_table.add_column(justify="right", width=20)

        agent_text = Text()
        if self._current_agent:
            agent_text.append(
                f"  {self._current_agent}", style=f"bold {THEME['accent']}"
            )
        else:
            agent_text.append("  Ready", style=THEME["muted"])

        progress_text = Text()
        if self._step_total > 0:
            progress_text.append(
                f"Step {self._step_current}/{self._step_total}",
                style=THEME["fg"],
            )
            progress_text.append("  ", style="")

            filled = int((self._step_current / self._step_total) * 10)
            progress_text.append("█" * filled, style=THEME["success"])
            progress_text.append("░" * (10 - filled), style=THEME["muted"])

            pct = int((self._step_current / self._step_total) * 100)
            progress_text.append(f"  {pct}%", style=THEME["muted"])

        hint_text = Text("ESC to cancel  ", style=THEME["muted"])

        status_table.add_row(agent_text, progress_text, hint_text)

        return Panel(
            status_table,
            box=box.HEAVY_HEAD,
            border_style=THEME["border"],
            padding=(0, 0),
        )

    def _create_layout(self) -> Layout:
        """Create the layout structure once."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="status", size=3),
        )
        layout["body"].split_column(
            Layout(name="task", size=3),
            Layout(name="action", size=4),
            Layout(name="log", ratio=1),
        )
        return layout

    def _update_layout(self) -> None:
        """Update the layout content without recreating structure."""
        if self._layout is None:
            return
        self._layout["header"].update(self._build_header())
        self._layout["task"].update(self._build_task_panel())
        self._layout["action"].update(self._build_action_panel())
        self._layout["log"].update(self._build_log_panel())
        self._layout["status"].update(self._build_status_bar())

    def start_dashboard(self) -> None:
        """Start the live dashboard display."""
        if self.verbosity == VerbosityLevel.QUIET:
            return

        if self._is_running:
            return

        self._layout = self._create_layout()
        self._update_layout()
        self._is_running = True
        self._live = Live(
            self._layout,
            console=self.console,
            refresh_per_second=8,
            screen=False,
            transient=False,
        )
        self._live.start()

    def stop_dashboard(self) -> None:
        """Stop the live dashboard display."""
        if not self._is_running:
            return
        self._is_running = False
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        self._layout = None

    def refresh(self) -> None:
        """Manually refresh the dashboard with throttling."""
        if not self._is_running or self._live is None:
            return

        now = time.time()
        if now - self._last_refresh < self._min_refresh_interval:
            return

        with self._update_lock:
            self._last_refresh = now
            self._update_layout()

    def set_task(self, task: str) -> None:
        """Set the current task being executed."""
        self._task = task
        self._status = "working"
        self.add_log_entry(ActionType.PLAN, f"Task received: {task[:50]}...")
        self.refresh()

    def set_agent(self, agent_name: str) -> None:
        """Set the current active agent."""
        self._current_agent = agent_name
        self.add_log_entry(ActionType.EXECUTE, f"{agent_name} activated")
        self.refresh()

    def set_action(
        self,
        action: str,
        target: Optional[str] = None,
        progress: float = 0,
    ) -> None:
        """Set the current action being performed."""
        self._current_action = action
        self._action_target = target
        self._progress.set_progress(progress)
        self.refresh()

    def clear_action(self) -> None:
        """Clear the current action display."""
        self._current_action = None
        self._action_target = None
        self._progress.set_progress(0)
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
        """
        Add an entry to the action log.

        Returns:
            Index of the added entry for later updates.
        """
        entry = ActionLogEntry(
            action_type=action_type,
            message=message,
            target=target,
            status=status,
        )
        self._action_log.append(entry)

        if len(self._action_log) > 50:
            self._action_log = self._action_log[-50:]

        self.refresh()
        return len(self._action_log) - 1

    def update_log_entry(self, index: int, status: str) -> None:
        """Update the status of a log entry."""
        if 0 <= index < len(self._action_log):
            self._action_log[index].status = status
            self.refresh()

    def complete_task(self, success: bool, message: Optional[str] = None) -> None:
        """Mark the current task as complete."""
        self._status = "ready"
        self._current_action = None
        self._action_target = None
        self._step_current = 0
        self._step_total = 0

        if success:
            self.add_log_entry(
                ActionType.COMPLETE,
                message or "Task completed successfully",
                status="complete",
            )
        else:
            self.add_log_entry(
                ActionType.ERROR,
                message or "Task failed",
                status="error",
            )

        self.refresh()


dashboard = DashboardManager()
console = dashboard.console


def verbose_print(message: str) -> None:
    """Print only in verbose mode, suppressed when dashboard is running."""
    if dashboard._is_running:
        return
    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        console.print(f"  [{THEME['muted']}]{message}[/]")


_key_bindings = KeyBindings()
_voice_mode_enabled = {"value": False}


@_key_bindings.add("enter")
def _(event):
    """Handle Enter key - submit the input."""
    event.current_buffer.validate_and_handle()


@_key_bindings.add("c-j")
def _(event):
    """Handle Ctrl+J - insert newline."""
    event.current_buffer.insert_text("\n")


@_key_bindings.add("escape", "enter")
def _(event):
    """Handle Alt/Option+Enter - insert newline."""
    event.current_buffer.insert_text("\n")


@_key_bindings.add("f5")
def _(event):
    """Handle F5 - toggle voice input mode."""
    _voice_mode_enabled["value"] = not _voice_mode_enabled["value"]
    mode = "Voice" if _voice_mode_enabled["value"] else "Text"
    print_info(f"Switched to {mode} mode")


_prompt_session = PromptSession(
    history=None,
    multiline=True,
    key_bindings=_key_bindings,
)


def print_banner() -> None:
    """Display minimal, elegant startup banner."""
    if dashboard.verbosity == VerbosityLevel.QUIET:
        return

    console.print()

    title = Text()
    title.append("◆ ", style=f"bold {THEME['secondary']}")
    title.append("Computer Use Agent", style=f"bold {THEME['primary']}")

    console.print(title)

    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        subtitle = Text()
        subtitle.append("  Autonomous Desktop & Web Automation", style=THEME["muted"])
        console.print(subtitle)
        console.print()

        hints = Text()
        hints.append("  ")
        hints.append("F5", style=f"bold {THEME['accent']}")
        hints.append(" voice  ", style=THEME["muted"])
        hints.append("Alt+↵", style=f"bold {THEME['accent']}")
        hints.append(" newline  ", style=THEME["muted"])
        hints.append("Ctrl+C", style=f"bold {THEME['accent']}")
        hints.append(" cancel", style=THEME["muted"])
        console.print(hints)

    console.print()


def print_section_header(title: str, icon: str = "") -> None:
    """Print styled section header."""
    if dashboard.verbosity == VerbosityLevel.QUIET:
        return

    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        console.print()
        text = Text()
        if icon:
            text.append(f"{icon} ", style=THEME["secondary"])
        text.append(title, style=f"bold {THEME['primary']}")
        console.print(text)
        console.print("─" * 50, style=THEME["border"])


def print_platform_info(capabilities) -> None:
    """Display platform capabilities in compact format."""
    if dashboard.verbosity == VerbosityLevel.QUIET:
        return

    if dashboard.verbosity == VerbosityLevel.VERBOSE:
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
        info_line = Text()
        info_line.append("  Platform: ", style=THEME["muted"])
        info_line.append(
            f"{capabilities.os_type.title()} {capabilities.os_version}",
            style=THEME["fg"],
        )
        info_line.append(" | Display: ", style=THEME["muted"])
        info_line.append(
            f"{capabilities.screen_resolution[0]}×{capabilities.screen_resolution[1]}",
            style=THEME["fg"],
        )
        console.print(info_line)


def print_status_overview(title: str, items: dict) -> None:
    """Render a concise key-value overview panel."""
    if dashboard.verbosity == VerbosityLevel.QUIET:
        return

    if not items:
        return

    if dashboard.verbosity == VerbosityLevel.VERBOSE:
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
        info_parts = []
        for label, value in list(items.items())[:3]:
            info_parts.append(f"{label}: {value}")

        info_line = Text()
        info_line.append("  ", style="")
        info_line.append(" | ".join(info_parts), style=THEME["muted"])
        console.print(info_line)


def print_agent_start(agent_name: str) -> None:
    """Announce agent execution."""
    dashboard.set_agent(agent_name)

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("▸ ", style=f"bold {THEME['secondary']}")
        text.append(agent_name, style=f"bold {THEME['primary']}")
        console.print()
        console.print(text)


def print_step(step: int, action: str, target: str, reasoning: str) -> None:
    """Display agent step with clean formatting."""
    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        text = Text()
        text.append(f"  {step}. ", style=THEME["muted"])
        text.append(action, style=f"bold {THEME['accent']}")
        text.append(" → ", style=THEME["muted"])
        text.append(target, style=THEME["fg"])
        console.print(text)

        if reasoning:
            console.print(f"     [{THEME['muted']}]{reasoning}[/]")


def print_success(message: str) -> None:
    """Print success message."""
    dashboard.add_log_entry(ActionType.COMPLETE, message, status="complete")

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("  ✓ ", style=f"bold {THEME['success']}")
        text.append(message, style=THEME["success"])
        console.print(text)


def print_failure(message: str) -> None:
    """Print failure message."""
    dashboard.add_log_entry(ActionType.ERROR, message, status="error")

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("  ✗ ", style=f"bold {THEME['error']}")
        text.append(message, style=THEME["error"])
        console.print(text)


def print_info(message: str) -> None:
    """Print info message."""
    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        dashboard.add_log_entry(ActionType.ANALYZE, message, status="complete")

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("  ℹ ", style=f"bold {THEME['accent']}")
        text.append(message, style=THEME["accent"])
        console.print(text)


def print_warning(message: str) -> None:
    """Print warning message."""
    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("  ⚠ ", style=f"bold {THEME['warning']}")
        text.append(message, style=THEME["warning"])
        console.print(text)


@contextmanager
def action_spinner(action: str, target: str):
    """
    Context manager that shows a spinner during an action.
    Updates the dashboard action panel when running.
    """
    action_type = _infer_action_type(action)
    log_idx = dashboard.add_log_entry(action_type, action, target, status="pending")
    dashboard.set_action(action, target, progress=50)

    try:
        if dashboard._is_running:
            yield
        else:
            status_text = Text()
            status_text.append(f"  ● {action} ", style=f"bold {THEME['accent']}")
            status_text.append(f"'{target}'", style=THEME["warning"])

            spinner = Spinner("dots", text=status_text)

            with Live(spinner, console=console, refresh_per_second=12, transient=True):
                yield
    finally:
        dashboard.update_log_entry(log_idx, "complete")
        dashboard.clear_action()


def _infer_action_type(action: str) -> ActionType:
    """Infer the action type from the action string."""
    action_lower = action.lower()
    if "click" in action_lower:
        return ActionType.CLICK
    elif "type" in action_lower or "typing" in action_lower:
        return ActionType.TYPE
    elif "scroll" in action_lower:
        return ActionType.SCROLL
    elif "open" in action_lower:
        return ActionType.OPEN
    elif "read" in action_lower:
        return ActionType.READ
    elif "search" in action_lower or "scan" in action_lower:
        return ActionType.SEARCH
    elif "navigate" in action_lower:
        return ActionType.NAVIGATE
    elif "analyz" in action_lower:
        return ActionType.ANALYZE
    else:
        return ActionType.EXECUTE


@contextmanager
def task_progress(title: str, total: int = 0):
    """Context manager for multi-step task progress."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn(f"[{THEME['accent']}]{title}[/]"),
        BarColumn(complete_style=THEME["success"], finished_style=THEME["success"]),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    )

    with progress:
        task_id = progress.add_task(title, total=total or 100)

        class ProgressUpdater:
            """Helper class for updating progress."""

            def advance(self, amount: int = 1) -> None:
                """Advance progress by amount."""
                progress.advance(task_id, amount)

            def complete(self) -> None:
                """Complete the progress."""
                progress.update(task_id, completed=total or 100)

        yield ProgressUpdater()


def print_action(action: str, target: str, detail: Optional[str] = None) -> None:
    """Print action being taken (non-blocking, instant display)."""
    action_type = _infer_action_type(action)
    dashboard.add_log_entry(action_type, action, target, status="pending")

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("  → ", style=f"bold {THEME['secondary']}")
        text.append(f"{action} ", style=f"bold {THEME['accent']}")
        text.append(f"'{target}'", style=THEME["warning"])
        if detail:
            text.append(f" ({detail})", style=THEME["muted"])
        console.print(text)


def print_action_result(success: bool, message: str) -> None:
    """Print action result."""
    if dashboard._action_log:
        dashboard.update_log_entry(
            len(dashboard._action_log) - 1,
            "complete" if success else "error",
        )

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        if success:
            text = Text()
            text.append("    ✓ ", style=f"bold {THEME['success']}")
            text.append(message, style=THEME["muted"])
            console.print(text)
        else:
            text = Text()
            text.append("    ✗ ", style=f"bold {THEME['error']}")
            text.append(message, style=THEME["muted"])
            console.print(text)


def print_command_approval(command: str) -> str:
    """Display command approval request with clean design."""
    was_running = dashboard._is_running
    if was_running:
        dashboard.stop_dashboard()

    console.print()

    panel_content = Text()
    panel_content.append("Command: ", style=f"bold {THEME['warning']}")
    panel_content.append(command, style=THEME["fg"])
    panel_content.append("\n\n")
    panel_content.append("1", style=f"bold {THEME['success']}")
    panel_content.append(" Allow once  ", style=THEME["fg"])
    panel_content.append("2", style=f"bold {THEME['accent']}")
    panel_content.append(" Allow session  ", style=THEME["fg"])
    panel_content.append("3", style=f"bold {THEME['error']}")
    panel_content.append(" Deny", style=THEME["fg"])

    panel = Panel(
        panel_content,
        title=f"[{THEME['warning']}]Approval Required[/]",
        border_style=THEME["warning"],
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)

    choice = console.input(f"[bold {THEME['fg']}]Choice (1/2/3):[/] ").strip()

    if was_running:
        dashboard.start_dashboard()

    return choice


def print_handoff(from_agent: str, to_agent: str, reason: str) -> None:
    """Display agent handoff."""
    dashboard.set_agent(to_agent)
    dashboard.add_log_entry(
        ActionType.EXECUTE,
        f"Handoff: {from_agent} → {to_agent}",
        reason,
        status="complete",
    )

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        console.print()
        text = Text()
        text.append("  ↪ ", style=f"bold {THEME['secondary']}")
        text.append(from_agent, style=THEME["accent"])
        text.append(" → ", style=THEME["muted"])
        text.append(to_agent, style=THEME["accent"])
        if reason:
            text.append(f" ({reason})", style=THEME["muted"])
        console.print(text)


def print_task_result(result) -> None:
    """Display final task result with clean formatting."""
    if hasattr(result, "overall_success"):
        success = result.overall_success
        result_text = getattr(result, "result", None)
        error = getattr(result, "error", None)
    else:
        success = result.get("overall_success", False)
        result_text = result.get("result")
        error = result.get("error")

    dashboard.complete_task(success, error if not success else None)

    if dashboard._is_running:
        return

    console.print()

    if success:
        header = Text()
        header.append("✓ ", style=f"bold {THEME['success']}")
        header.append("Complete", style=f"bold {THEME['success']}")
        console.print(header)
    else:
        header = Text()
        header.append("✗ ", style=f"bold {THEME['error']}")
        header.append("Failed", style=f"bold {THEME['error']}")
        console.print(header)
        if error:
            console.print(f"  [{THEME['error']}]{error}[/]")

    if result_text and isinstance(result_text, str):
        console.print()
        shortened = result_text[:500] + "..." if len(result_text) > 500 else result_text
        console.print(f"  [{THEME['muted']}]{shortened}[/]")

    console.print()


def print_action_history(history: list) -> None:
    """Display action history in compact format."""
    if not history or dashboard.verbosity == VerbosityLevel.QUIET:
        return

    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        console.print()
        console.print(f"  [{THEME['muted']}]Recent actions:[/]")

        for action in history[-5:]:
            status = "✓" if action.get("success") else "✗"
            style = THEME["success"] if action.get("success") else THEME["error"]
            console.print(
                f"    [{style}]{status}[/] {action.get('action', '')} → {action.get('target', '')[:30]}"
            )


def print_webhook_status(port: int, status: str = "starting") -> None:
    """Display webhook server status."""
    if dashboard.verbosity == VerbosityLevel.QUIET:
        return

    if status == "ready":
        if dashboard.verbosity == VerbosityLevel.VERBOSE:
            console.print(f"  [{THEME['success']}]✓ Webhook ready on port {port}[/]")
    elif status == "failed":
        console.print(
            f"  [{THEME['error']}]✗ Could not start webhook on port {port}[/]"
        )


def print_twilio_config_status(
    is_configured: bool, phone_number: Optional[str] = None
) -> None:
    """Display Twilio configuration status."""
    if dashboard.verbosity == VerbosityLevel.QUIET:
        return

    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        if is_configured and phone_number:
            console.print(f"  [{THEME['success']}]✓ Twilio: {phone_number}[/]")
        else:
            console.print(f"  [{THEME['muted']}]Twilio not configured[/]")


def print_element_found(
    element_type: str, label: str, coords: Optional[tuple] = None
) -> None:
    """Print element found notification."""
    if dashboard.verbosity == VerbosityLevel.VERBOSE:
        dashboard.add_log_entry(
            ActionType.SEARCH,
            f"Found {element_type}",
            label,
            status="complete",
        )

        if not dashboard._is_running:
            text = Text()
            text.append("    ◎ ", style=THEME["secondary"])
            text.append(f"Found {element_type} ", style=THEME["muted"])
            text.append(f"'{label}'", style=THEME["fg"])
            if coords:
                text.append(f" at ({coords[0]}, {coords[1]})", style=THEME["muted"])
            console.print(text)


def print_thinking(message: str = "Analyzing...") -> None:
    """Print thinking/analyzing indicator."""
    dashboard.set_action("Analyzing", message)

    if (
        dashboard.verbosity.value >= VerbosityLevel.NORMAL.value
        and not dashboard._is_running
    ):
        text = Text()
        text.append("  ◌ ", style=f"bold {THEME['secondary']}")
        text.append(message, style=THEME["muted"])
        console.print(text)


async def get_voice_input() -> Optional[str]:
    """Capture voice input using Deepgram streaming API."""
    try:
        from ..services.voice_input_service import VoiceInputService
        from ..services.audio_capture import AudioCapture

        if not VoiceInputService.check_api_key_configured():
            print_failure("DEEPGRAM_API_KEY not found")
            return None

        if not AudioCapture.check_microphone_available():
            print_failure("No microphone detected")
            return None

        console.print()
        console.print(
            f"  [{THEME['success']}]Listening...[/] [{THEME['muted']}](Enter to finish)[/]"
        )

        max_width = console.width - 10

        def on_interim(text: str) -> None:
            display_text = text[:max_width] if len(text) > max_width else text
            padding = " " * max(0, max_width - len(display_text))
            sys.stdout.write(f"\r  [{THEME['accent']}]▸ {display_text}[/]{padding}")
            sys.stdout.flush()

        voice_service = VoiceInputService()
        language = os.getenv("VOICE_INPUT_LANGUAGE", "multi")
        started = await voice_service.start_transcription(
            interim_callback=on_interim, language=language
        )

        if not started:
            print_failure(f"Voice input failed: {voice_service.get_error()}")
            return None

        await asyncio.sleep(0.5)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, input)
        except (KeyboardInterrupt, EOFError):
            pass

        result = await voice_service.stop_transcription()
        sys.stdout.write("\n")
        sys.stdout.flush()

        if result:
            print_success(f"Transcribed: {result}")
        else:
            print_warning("No speech detected")

        return result.strip() if result else None

    except ImportError as e:
        print_failure(f"Voice dependencies missing: {e}")
        return None
    except Exception as e:
        print_failure(f"Voice input error: {e}")
        return None


async def get_task_input(start_with_voice: bool = False) -> str:
    """
    Get task input with support for text and voice modes.

    Args:
        start_with_voice: Start in voice mode

    Returns:
        User's task input
    """
    global _voice_mode_enabled
    _voice_mode_enabled["value"] = start_with_voice

    try:
        while True:
            if _voice_mode_enabled["value"]:
                result = await get_voice_input()
                if result:
                    return result
                _voice_mode_enabled["value"] = False
                continue

            console.print()
            console.print(f"[{THEME['primary']}]What would you like me to do?[/]")

            prompt_text = FormattedText([(THEME["primary"], "❯ ")])

            task = await _prompt_session.prompt_async(
                prompt_text,
                prompt_continuation=FormattedText([("", "  ")]),
            )

            return task.strip()
    except (KeyboardInterrupt, EOFError):
        return "quit"
