"""
Pydantic schemas for structured agent outputs.
"""

from .gui_elements import UIElement, SemanticTarget
from .actions import GUIAction, ActionResult, SystemCommand
from .responses import AgentResponse
from .ocr_result import OCRResult, GPUInfo
from .element_result import DetectedElement
from .tool_types import (
    ActionExecutionResult,
    CapabilitiesSummary,
    ClickResult,
    TypeResult,
    ScrollResult,
    ReadResult,
    OpenAppResult,
)
from .task_output import TaskCompletionOutput
from .task_execution_result import TaskExecutionResult

__all__ = [
    "UIElement",
    "SemanticTarget",
    "GUIAction",
    "ActionResult",
    "SystemCommand",
    "AgentResponse",
    "OCRResult",
    "GPUInfo",
    "DetectedElement",
    "ActionExecutionResult",
    "CapabilitiesSummary",
    "ClickResult",
    "TypeResult",
    "ScrollResult",
    "ReadResult",
    "OpenAppResult",
    "TaskCompletionOutput",
    "TaskExecutionResult",
]
