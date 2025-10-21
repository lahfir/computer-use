"""
Task classification and analysis schemas.
"""

from enum import Enum
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """
    Types of tasks the agent can handle.
    """

    BROWSER = "browser"
    GUI = "gui"
    SYSTEM = "system"
    HYBRID = "hybrid"


class TaskAnalysis(BaseModel):
    """
    Task classification for agent delegation.
    Coordinator ONLY classifies - agents handle execution planning.
    """

    task_type: TaskType = Field(description="Primary type of task to execute")
    requires_browser: bool = Field(
        description="Whether the task needs web browser automation"
    )
    requires_gui: bool = Field(
        description="Whether the task needs native GUI interaction"
    )
    requires_system: bool = Field(
        description="Whether the task needs system/file operations"
    )
    reasoning: str = Field(description="One sentence explanation of classification")
