"""
Base renderer class for UI components.
"""

from abc import ABC, abstractmethod
from typing import Optional
from rich.console import Console, RenderableType
from ..state import TaskState, VerbosityLevel


class BaseRenderer(ABC):
    """Abstract base class for all UI renderers."""

    def __init__(
        self, console: Console, verbosity: VerbosityLevel = VerbosityLevel.NORMAL
    ):
        self.console = console
        self.verbosity = verbosity

    @abstractmethod
    def render(self, state: TaskState) -> Optional[RenderableType]:
        """Render the component based on current state."""
        pass

    def should_render(self, state: TaskState) -> bool:
        """Determine if the component should be rendered."""
        return True

    @property
    def is_verbose(self) -> bool:
        return self.verbosity == VerbosityLevel.VERBOSE

    @property
    def is_quiet(self) -> bool:
        return self.verbosity == VerbosityLevel.QUIET
