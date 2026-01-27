"""
Adaptive headset mascot loading animation.

Replaces all spinners in the app with a unified headset animation
that adapts to terminal width.
"""

import threading
import time
from contextlib import contextmanager
from typing import Generator, Literal

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from .theme import THEME


HEADSET_LARGE_ON = [
    "      ██████████████████╗      ",
    "    ██╔════════════════╗██    ",
    "  ██╔╝                  ╚██╗  ",
    "  ██║   ██████  ██████   ██║  ",
    "  ██║   ██████  ██████   ██║  ",
    "  ╚═╝   ╚═════╝ ╚═════╝  ╚═╝  ",
]

HEADSET_LARGE_OFF = [
    "      ██████████████████╗      ",
    "    ██╔════════════════╗██    ",
    "  ██╔╝                  ╚██╗  ",
    "  ██║   ░░░░░░  ░░░░░░   ██║  ",
    "  ██║   ░░░░░░  ░░░░░░   ██║  ",
    "  ╚═╝   ╚═════╝ ╚═════╝  ╚═╝  ",
]

HEADSET_MEDIUM_ON = [
    "    ██████████████╗    ",
    "  ██╔════════════╗██  ",
    "██╔╝              ╚██╗",
    "██║  ████╗  ████╗  ██║",
    "██║  ████║  ████║  ██║",
    "╚═╝  ╚═══╝  ╚═══╝  ╚═╝",
]

HEADSET_MEDIUM_OFF = [
    "    ██████████████╗    ",
    "  ██╔════════════╗██  ",
    "██╔╝              ╚██╗",
    "██║  ░░░░╗  ░░░░╗  ██║",
    "██║  ░░░░║  ░░░░║  ██║",
    "╚═╝  ╚═══╝  ╚═══╝  ╚═╝",
]

HEADSET_SMALL_ON = [
    "  ████████╗  ",
    " ██╔════╗██ ",
    "██║ ██ ██ ██║",
    "╚═╝ ╚╝ ╚╝ ╚═╝",
]

HEADSET_SMALL_OFF = [
    "  ████████╗  ",
    " ██╔════╗██ ",
    "██║ ░░ ░░ ██║",
    "╚═╝ ╚╝ ╚╝ ╚═╝",
]

HEADSET_MINI_ON = [
    "╔══════╗",
    "║ ▓▓▓▓ ║",
    "╚══════╝",
]

HEADSET_MINI_OFF = [
    "╔══════╗",
    "║ ░░░░ ║",
    "╚══════╝",
]

HEADSET_INLINE_FRAMES = ["◐", "◓", "◑", "◒"]

SizeType = Literal["auto", "large", "medium", "small", "mini", "inline"]


def _get_size_for_width(width: int) -> SizeType:
    """Determine appropriate headset size based on terminal width."""
    if width >= 80:
        return "large"
    elif width >= 60:
        return "medium"
    elif width >= 40:
        return "small"
    elif width >= 20:
        return "mini"
    return "inline"


def _get_frames_for_size(size: SizeType) -> tuple[list[str], list[str]]:
    """Get on/off frames for a given size."""
    frames_map = {
        "large": (HEADSET_LARGE_ON, HEADSET_LARGE_OFF),
        "medium": (HEADSET_MEDIUM_ON, HEADSET_MEDIUM_OFF),
        "small": (HEADSET_SMALL_ON, HEADSET_SMALL_OFF),
        "mini": (HEADSET_MINI_ON, HEADSET_MINI_OFF),
    }
    return frames_map.get(size, (HEADSET_MEDIUM_ON, HEADSET_MEDIUM_OFF))


class HeadsetLoader:
    """
    Adaptive headset loading animation.

    Automatically selects size based on terminal width.
    Replaces all spinners with unified headset branding.
    """

    def __init__(
        self,
        console: Console | None = None,
        message: str = "",
        blink_interval: float = 0.4,
        size: SizeType = "auto",
        centered: bool = True,
    ):
        """
        Initialize the headset loader.

        Args:
            console: Rich console instance
            message: Message to display below the headset
            blink_interval: Time between blinks in seconds
            size: Size variant ("auto", "large", "medium", "small", "mini", "inline")
            centered: Whether to center the headset in terminal
        """
        self._console = console or Console()
        self._message = message
        self._blink_interval = blink_interval
        self._size = size
        self._centered = centered
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._frame_idx = 0

    def _get_actual_size(self) -> SizeType:
        """Get the actual size to use (resolve 'auto')."""
        if self._size == "auto":
            return _get_size_for_width(self._console.width)
        return self._size

    def _render_frame(self, is_on: bool) -> Group:
        """Render a single animation frame."""
        actual_size = self._get_actual_size()

        if actual_size == "inline":
            return self._render_inline_frame()

        frame_on, frame_off = _get_frames_for_size(actual_size)
        frame_lines = frame_on if is_on else frame_off

        c_header = THEME.get("header", "#ffffff")
        c_dim = THEME.get("hud_dim", "#8b949e")
        c_muted = THEME.get("muted", "#7d8590")
        c_active = THEME.get("hud_active", "#58a6ff")

        width = self._console.width
        lines = []

        for line in frame_lines:
            styled_line = Text()

            if self._centered:
                art_width = len(line)
                padding = max(0, (width - art_width) // 2)
                styled_line.append(" " * padding)

            for char in line:
                if char == "░":
                    styled_line.append(char, style=c_muted)
                elif char in "██":
                    styled_line.append(char, style=f"bold {c_header}")
                elif char in "╔╗╚╝║╝═":
                    styled_line.append(char, style=c_active)
                else:
                    styled_line.append(char, style=c_dim)

            lines.append(styled_line)

        if self._message:
            msg_line = Text()
            if self._centered:
                msg_padding = max(0, (width - len(self._message)) // 2)
                msg_line.append(" " * msg_padding)
            msg_line.append(self._message, style=f"italic {c_dim}")
            lines.append(Text(""))
            lines.append(msg_line)

        return Group(*lines)

    def _render_inline_frame(self) -> Group:
        """Render inline spinner frame."""
        c_active = THEME.get("hud_active", "#58a6ff")
        c_dim = THEME.get("hud_dim", "#8b949e")

        frame_char = HEADSET_INLINE_FRAMES[self._frame_idx % len(HEADSET_INLINE_FRAMES)]

        line = Text()
        line.append(f"  {frame_char} ", style=f"bold {c_active}")
        if self._message:
            line.append(self._message, style=c_dim)

        return Group(line)

    def _animation_loop(self) -> None:
        """Main animation loop."""
        is_on = True

        with Live(
            self._render_frame(is_on),
            console=self._console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            while self._running:
                live.update(self._render_frame(is_on))
                is_on = not is_on
                self._frame_idx += 1
                self._stop_event.wait(self._blink_interval)

    def start(self) -> None:
        """Start the loading animation."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._animation_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the loading animation."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=0.2)
        self._thread = None

    def set_message(self, message: str) -> None:
        """Update the loading message."""
        self._message = message

    @classmethod
    @contextmanager
    def context(
        cls,
        message: str = "",
        size: SizeType = "auto",
        console: Console | None = None,
        centered: bool = True,
    ) -> Generator["HeadsetLoader", None, None]:
        """
        Context manager for the headset loader.

        Args:
            message: Message to display
            size: Size variant
            console: Rich console
            centered: Center the headset

        Yields:
            The loader instance
        """
        loader = cls(console=console, message=message, size=size, centered=centered)
        loader.start()
        try:
            yield loader
        finally:
            loader.stop()


@contextmanager
def headset_spinner(
    console: Console,
    message: str,
    size: SizeType = "auto",
) -> Generator[HeadsetLoader, None, None]:
    """
    Drop-in replacement for startup_spinner using headset animation.

    Args:
        console: Rich console
        message: Spinner message
        size: Size variant

    Yields:
        HeadsetLoader instance
    """
    loader = HeadsetLoader(
        console=console,
        message=message,
        size=size,
        centered=True,
    )
    loader.start()
    try:
        yield loader
    finally:
        loader.stop()


@contextmanager
def action_headset(
    console: Console,
    action: str,
    target: str = "",
    size: SizeType = "mini",
) -> Generator[HeadsetLoader, None, None]:
    """
    Drop-in replacement for action_spinner using headset animation.

    Args:
        console: Rich console
        action: Action being performed
        target: Target of the action
        size: Size variant (defaults to mini for actions)

    Yields:
        HeadsetLoader instance
    """
    message = f"{action} {target}".strip() if target else action
    loader = HeadsetLoader(
        console=console,
        message=message,
        size=size,
        centered=False,
        blink_interval=0.3,
    )
    loader.start()
    try:
        yield loader
    finally:
        loader.stop()


def demo() -> None:
    """Demo all headset sizes."""
    console = Console()

    console.print("\n[bold cyan]Large (80+ cols):[/bold cyan]")
    with HeadsetLoader.context(message="Initializing systems...", size="large"):
        time.sleep(2)

    console.print("\n[bold cyan]Medium (60+ cols):[/bold cyan]")
    with HeadsetLoader.context(message="Loading agents...", size="medium"):
        time.sleep(2)

    console.print("\n[bold cyan]Small (40+ cols):[/bold cyan]")
    with HeadsetLoader.context(message="Connecting...", size="small"):
        time.sleep(2)

    console.print("\n[bold cyan]Mini (20+ cols):[/bold cyan]")
    with HeadsetLoader.context(message="Working...", size="mini"):
        time.sleep(2)

    console.print("\n[bold cyan]Inline:[/bold cyan]")
    with HeadsetLoader.context(message="Processing request...", size="inline"):
        time.sleep(2)

    console.print("\n[bold cyan]Auto (adapts to terminal):[/bold cyan]")
    with HeadsetLoader.context(message="Auto-sizing based on terminal width..."):
        time.sleep(2)

    console.print("\n[green]Done![/green]")


if __name__ == "__main__":
    demo()
