"""
CrewAI-compatible tool implementations.
All tools return ActionResult (Pydantic) for type safety.
"""

from .instrumented_tool import InstrumentedBaseTool
from .gui_basic_tools import (
    TakeScreenshotTool,
    OpenApplicationTool,
    ReadScreenTextTool,
    ScrollTool,
    ListRunningAppsTool,
    CheckAppRunningTool,
    GetAccessibleElementsTool,
    SearchElementsTool,
    GetWindowImageTool,
    RequestHumanInputTool,
)
from .gui_interaction_tools import (
    ClickElementTool,
    TypeTextTool,
)
from .web_tools import WebAutomationTool
from .system_tools import ExecuteShellCommandTool
from .capability_tools import FindApplicationTool
from .coding_tools import CodingAgentTool
from .observation_tools import GetSystemStateTool, VerifyAppFocusedTool

__all__ = [
    "InstrumentedBaseTool",
    "TakeScreenshotTool",
    "ClickElementTool",
    "TypeTextTool",
    "OpenApplicationTool",
    "ReadScreenTextTool",
    "ScrollTool",
    "ListRunningAppsTool",
    "CheckAppRunningTool",
    "GetAccessibleElementsTool",
    "SearchElementsTool",
    "GetWindowImageTool",
    "RequestHumanInputTool",
    "WebAutomationTool",
    "ExecuteShellCommandTool",
    "FindApplicationTool",
    "CodingAgentTool",
    "GetSystemStateTool",
    "VerifyAppFocusedTool",
]
