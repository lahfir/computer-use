"""
Pydantic schemas for structured agent outputs.
"""

from .task_analysis import TaskType, TaskAnalysis
from .gui_elements import UIElement, SemanticTarget
from .actions import GUIAction, ActionResult, SystemCommand
from .responses import AgentResponse

__all__ = [
    "TaskType",
    "TaskAnalysis",
    "UIElement",
    "SemanticTarget",
    "GUIAction",
    "ActionResult",
    "SystemCommand",
    "AgentResponse",
]
