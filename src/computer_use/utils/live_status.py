"""
Live status module - consolidated into ui.py.

This module re-exports components from ui.py for backwards compatibility.
All live status functionality is now part of the main DashboardManager in ui.py.
"""

from .ui import (
    ActionType,
    DashboardManager,
    ShimmerText,
    AnimatedProgress,
    dashboard,
    console,
    THEME,
)


class LiveStatus(DashboardManager):
    """
    Backwards-compatible alias for DashboardManager.

    .. deprecated::
        Use DashboardManager from ui.py instead.
    """

    pass


class ActionProgress:
    """
    Track and display multi-step action progress.
    Simplified wrapper around AnimatedProgress.
    """

    def __init__(self, total_steps: int, title: str = "Progress"):
        """
        Initialize progress tracker.

        Args:
            total_steps: Total number of steps
            title: Progress title
        """
        self.total = total_steps
        self.current = 0
        self.title = title

    def __enter__(self):
        dashboard.set_action(self.title, f"0/{self.total}", progress=0)
        return self

    def __exit__(self, *args):
        dashboard.clear_action()

    def advance(self, step_name: str = None) -> None:
        """
        Advance progress by one step.

        Args:
            step_name: Optional name of completed step
        """
        self.current += 1
        progress = int((self.current / self.total) * 100)
        dashboard.set_action(
            self.title, f"{self.current}/{self.total}", progress=progress
        )


def format_element_info(element_type: str, label: str, location: tuple = None) -> str:
    """
    Format element information for display.

    Args:
        element_type: Type of element (button, text, etc.)
        label: Element label
        location: Optional (x, y) coordinates

    Returns:
        Formatted string
    """
    parts = [f"{element_type}"]
    if label:
        parts.append(f'"{label}"')
    if location:
        parts.append(f"at ({location[0]}, {location[1]})")
    return " ".join(parts)


live_status = dashboard


__all__ = [
    "ActionType",
    "DashboardManager",
    "LiveStatus",
    "ShimmerText",
    "AnimatedProgress",
    "ActionProgress",
    "dashboard",
    "live_status",
    "console",
    "THEME",
    "format_element_info",
]
