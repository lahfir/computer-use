"""
Render manager for terminal output.

This module provides a singleton that coordinates terminal output. Unlike the
previous Layout-based Live approach, this version uses normal scrolling output
with a simple status line that updates in place.
"""

from __future__ import annotations

import sys
import threading
from typing import Optional

from rich.console import Console, RenderableType
from rich.text import Text

from ..headset_loader import HeadsetLoader
from .resize_handler import setup_resize_handler


class RenderManager:
    """Coordinate all terminal output with a simple status spinner."""

    _instance: Optional["RenderManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "RenderManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.console = Console(force_terminal=True, force_interactive=True)
        self._render_lock = threading.Lock()

        self._status: Optional[HeadsetLoader] = None
        self._status_text: str = ""
        self._is_running: bool = False

        setup_resize_handler(self._on_resize)

    def _on_resize(self, cols: int, rows: int) -> None:
        """Handle terminal resize - currently a no-op for simple output."""
        _ = cols, rows

    def bind_console(self, console: Console) -> None:
        """Bind an external Console instance for all rendering."""
        with self._render_lock:
            self.console = console

    def start(self) -> None:
        """Mark rendering as active."""
        with self._render_lock:
            self._is_running = True

    def stop(self) -> None:
        """Stop rendering and clean up status."""
        with self._render_lock:
            self._is_running = False
            if self._status is not None:
                try:
                    self._status.stop()
                except Exception:
                    pass
                self._status = None

    def clear(self) -> None:
        """Clear status (output history is not tracked in this mode)."""
        with self._render_lock:
            self._status_text = ""
            if self._status is not None:
                try:
                    self._status.stop()
                except Exception:
                    pass
                self._status = None

    def stop_status(self) -> None:
        """Explicitly stop the status spinner."""
        with self._render_lock:
            self._status_text = ""
            if self._status is not None:
                try:
                    self._status.stop()
                except Exception:
                    pass
                self._status = None

    def set_header(self, renderable: RenderableType) -> None:
        """
        Print header content.

        In pass-through mode, headers are printed once when set.
        """
        if not self._is_running:
            return
        with self._render_lock:
            self._pause_status()
            self.console.print(renderable)
            sys.stdout.flush()

    def set_status(self, renderable: RenderableType) -> None:
        """
        Update the status line.

        This uses HeadsetLoader to show an animated status.
        Pass empty text to stop the animation.
        """
        if not self._is_running:
            return
        with self._render_lock:
            if isinstance(renderable, Text):
                self._status_text = renderable.plain
            else:
                self._status_text = str(renderable)

            if not self._status_text.strip():
                if self._status is not None:
                    try:
                        self._status.stop()
                    except Exception:
                        pass
                    self._status = None
                return

            if self._status is None:
                self._status = HeadsetLoader(
                    console=self.console,
                    message=self._status_text,
                    size="inline",
                    centered=False,
                )
                self._status.start()
            else:
                self._status.set_message(self._status_text)

    def append(self, renderable: RenderableType) -> None:
        """Append a renderable to output (prints immediately)."""
        if not self._is_running:
            return
        with self._render_lock:
            self._pause_status()
            self.console.print(renderable)
            sys.stdout.flush()
            self._resume_status()

    def append_text(self, content: str) -> None:
        """Append plain text content to output."""
        self.append(Text.from_markup(content))

    def _pause_status(self) -> None:
        """Temporarily hide status spinner before printing."""
        if self._status is None:
            return

        try:
            self._status.stop()
        except Exception:
            pass

        self._status = None

    def _resume_status(self) -> None:
        """Resume status spinner after printing."""
        if self._status_text and self._is_running:
            self._status = HeadsetLoader(
                console=self.console,
                message=self._status_text,
                size="inline",
                centered=False,
            )
            self._status.start()
