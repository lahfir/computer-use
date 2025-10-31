"""
Task classification and analysis schemas.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """
    Types of tasks the agent can handle.
    """

    BROWSER = "browser"
    GUI = "gui"
    SYSTEM = "system"
    HYBRID = "hybrid"


class AgentSubTask(BaseModel):
    """
    Specific sub-task for an individual agent.
    """

    objective: str = Field(
        description="Clear, specific objective for this agent to accomplish"
    )
    expected_output: str = Field(
        description="What this agent should produce or deliver to the next agent"
    )


class TaskAnalysis(BaseModel):
    """
    Task classification and breakdown for intelligent agent delegation.
    Coordinator analyzes the task and creates specific sub-tasks for each agent.
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
    direct_response: Optional[str] = Field(
        default=None,
        description="Direct response for conversational/informational queries that don't need agent execution",
    )
    browser_subtask: Optional[AgentSubTask] = Field(
        default=None,
        description="Specific sub-task for browser agent if required",
    )
    gui_subtask: Optional[AgentSubTask] = Field(
        default=None,
        description="Specific sub-task for GUI agent if required",
    )
    system_subtask: Optional[AgentSubTask] = Field(
        default=None,
        description="Specific sub-task for system agent if required",
    )
