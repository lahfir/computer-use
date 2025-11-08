"""
Task execution result schema.
"""

from pydantic import BaseModel, Field


class TaskExecutionResult(BaseModel):
    """
    Structured representation of a task execution.

    Attributes:
        task: Original task description provided by the user.
        result: Optional textual description of the execution result.
        overall_success: Whether the task finished successfully.
        error: Any error message captured during execution.
    """

    task: str = Field(..., description="Original task description")
    result: str | None = Field(None, description="Execution result")
    overall_success: bool = Field(..., description="Whether execution succeeded")
    error: str | None = Field(None, description="Error message if failed")
