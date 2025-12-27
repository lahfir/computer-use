"""
Rich-powered animations and spinners for real-time UI feedback.

Uses Rich's built-in Status, Spinner, and Progress for smooth animations.
"""

from contextlib import contextmanager
from typing import Generator, Optional

from rich.console import Console
from rich.spinner import Spinner
from rich.status import Status
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)

from .theme import THEME


SPINNER_STYLES = {
    "dots": "dots",
    "dots2": "dots2",
    "dots3": "dots3",
    "line": "line",
    "arc": "arc",
    "bouncingBar": "bouncingBar",
    "moon": "moon",
    "runner": "runner",
    "pong": "pong",
}


@contextmanager
def tool_spinner(
    console: Console, tool_name: str, spinner_style: str = "dots"
) -> Generator[Status, None, None]:
    """
    Context manager for tool execution with animated spinner.

    Usage:
        with tool_spinner(console, "open_application") as status:
            # do work
            status.update("Opening app...")
    """
    with console.status(
        f"[bold {THEME['tool_pending']}]⟳[/] {tool_name}",
        spinner=spinner_style,
        spinner_style=THEME["tool_pending"],
    ) as status:
        yield status


@contextmanager
def thinking_spinner(
    console: Console, message: str = "Thinking..."
) -> Generator[Status, None, None]:
    """
    Context manager for agent thinking with animated spinner.

    Usage:
        with thinking_spinner(console, "Analyzing...") as status:
            # agent thinks
            status.update("Planning approach...")
    """
    with console.status(
        f"[bold {THEME['thinking']}]┊[/] {message}",
        spinner="dots",
        spinner_style=THEME["thinking"],
    ) as status:
        yield status


@contextmanager
def action_status(
    console: Console, action: str, target: str = ""
) -> Generator[Status, None, None]:
    """
    Context manager for generic actions with spinner.

    Usage:
        with action_status(console, "Opening", "Calculator") as status:
            # do action
    """
    message = f"{action} {target}".strip()
    with console.status(
        f"[{THEME['tool_pending']}]⟳[/] {message}",
        spinner="dots",
        spinner_style=THEME["tool_pending"],
    ) as status:
        yield status


def create_spinner(text: str = "", style: str = "dots") -> Spinner:
    """
    Create a Rich Spinner for use in Live displays.

    Args:
        text: Text to show next to spinner
        style: Spinner style (dots, line, arc, etc.)
    """
    return Spinner(style, text=text, style=THEME["tool_pending"])


def create_task_progress(console: Console) -> Progress:
    """
    Create a progress bar for multi-step tasks.

    Usage:
        with create_task_progress(console) as progress:
            task = progress.add_task("Processing...", total=100)
            for i in range(100):
                progress.update(task, advance=1)
    """
    return Progress(
        SpinnerColumn(style=THEME["tool_pending"]),
        TextColumn("[bold {THEME['text']}]{task.description}[/]"),
        BarColumn(
            bar_width=40, style=THEME["muted"], complete_style=THEME["agent_active"]
        ),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


def create_tool_progress(console: Console) -> Progress:
    """
    Create a progress display for tool execution.

    Shows spinner + tool name + elapsed time.
    """
    return Progress(
        SpinnerColumn(style=THEME["tool_pending"]),
        TextColumn("[bold]{task.description}[/]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


class AnimatedStatus:
    """
    Reusable animated status that can be started/stopped.

    Usage:
        status = AnimatedStatus(console)
        status.start("Loading...")
        # do work
        status.update("Processing...")
        status.stop()
    """

    def __init__(self, console: Console, spinner_style: str = "dots"):
        self.console = console
        self.spinner_style = spinner_style
        self._status: Optional[Status] = None

    def start(self, message: str) -> None:
        """Start the animated status."""
        if self._status is None:
            self._status = self.console.status(
                message,
                spinner=self.spinner_style,
                spinner_style=THEME["tool_pending"],
            )
            self._status.start()

    def update(self, message: str) -> None:
        """Update the status message."""
        if self._status:
            self._status.update(message)

    def stop(self) -> None:
        """Stop the animated status."""
        if self._status:
            self._status.stop()
            self._status = None

    def __enter__(self) -> "AnimatedStatus":
        return self

    def __exit__(self, *args) -> None:
        self.stop()
