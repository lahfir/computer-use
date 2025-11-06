"""
CrewAI-compatible tool implementations.
All tools return ActionResult (Pydantic) for type safety.
"""

from .gui_basic_tools import (
    TakeScreenshotTool,
    OpenApplicationTool,
    ReadScreenTextTool,
    ScrollTool,
)
from .gui_interaction_tools import (
    ClickElementTool,
    TypeTextTool,
)
from .web_tools import WebAutomationTool
from .system_tools import ExecuteShellCommandTool
from .capability_tools import FindApplicationTool

__all__ = [
    "TakeScreenshotTool",
    "ClickElementTool",
    "TypeTextTool",
    "OpenApplicationTool",
    "ReadScreenTextTool",
    "ScrollTool",
    "WebAutomationTool",
    "ExecuteShellCommandTool",
    "FindApplicationTool",
]
