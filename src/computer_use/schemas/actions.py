"""
Action schemas for different agent types.
"""

from typing import Optional, List, Literal, Union, Any
from pydantic import BaseModel, Field
from .gui_elements import UIElement, SemanticTarget


class CommandResult(BaseModel):
    """
    Result from executing a shell command.
    """

    success: bool = Field(description="Whether command succeeded")
    command: str = Field(description="Command that was executed")
    output: Optional[str] = Field(default=None, description="stdout if successful")
    error: Optional[str] = Field(default=None, description="stderr or error message")


class ShellCommand(BaseModel):
    """
    Shell command decision from LLM for system agent.
    """

    command: str = Field(
        description="Shell command to execute (e.g., 'ls ~/Documents')"
    )
    reasoning: str = Field(description="Why this command is needed")
    is_complete: bool = Field(default=False, description="Is the task fully complete?")
    needs_handoff: bool = Field(
        default=False, description="Does this need another agent (e.g., GUI)?"
    )
    handoff_agent: Optional[str] = Field(
        default=None, description="Which agent to handoff to: 'gui' or 'browser'"
    )
    handoff_reason: Optional[str] = Field(
        default=None, description="Why handoff is needed"
    )


class GUIAction(BaseModel):
    """
    Structured action for GUI automation.
    """

    action: Literal[
        "click", "double_click", "right_click", "type", "scroll", "drag", "hotkey"
    ] = Field(description="Type of action to perform")
    target: Optional[UIElement] = Field(
        default=None, description="Detected UI element to interact with"
    )
    semantic_target: Optional[SemanticTarget] = Field(
        default=None, description="Semantic description of target if not yet located"
    )
    text: Optional[str] = Field(
        default=None, description="Text to type (for type action)"
    )
    key_combination: Optional[List[str]] = Field(
        default=None, description="Keys for hotkey action (e.g., ['cmd', 'c'])"
    )
    reasoning: str = Field(description="Explanation of why this action is being taken")
    fallback_strategy: Optional[str] = Field(
        default=None, description="What to do if this action fails"
    )


class GUIActionHistoryEntry(BaseModel):
    """
    Typed entry in action history for GUI agent.
    """

    step: int = Field(description="Step number")
    action: str = Field(description="Action type (click, type, etc.)")
    target: str = Field(description="Target element")
    success: bool = Field(description="Whether action succeeded")
    reasoning: str = Field(description="Why this action was taken")
    method: Optional[str] = Field(
        default=None, description="Method used (accessibility, ocr, etc.)"
    )


class SystemCommandHistoryEntry(BaseModel):
    """
    Typed entry in command history for System agent.
    """

    command: str = Field(description="Shell command executed")
    output: str = Field(description="Command output (stdout)")
    success: Optional[bool] = Field(
        default=None, description="Whether command succeeded"
    )


class HandoffContext(BaseModel):
    """
    Typed context for agent handoffs.
    """

    original_task: str = Field(description="Original task being attempted")
    failed_action: Optional[str] = Field(
        default=None, description="Action that failed (GUI)"
    )
    failed_target: Optional[str] = Field(
        default=None, description="Target element that failed (GUI)"
    )
    current_app: Optional[str] = Field(
        default=None, description="Current application (GUI)"
    )
    system_progress: Optional[List[SystemCommandHistoryEntry]] = Field(
        default=None, description="Command history (System)"
    )
    last_output: Optional[str] = Field(
        default=None, description="Last command output (System)"
    )
    loop_pattern: Optional[List[str]] = Field(
        default=None, description="Detected loop pattern"
    )
    repeated_action: Optional[dict[str, Any]] = Field(
        default=None, description="Action that was repeated"
    )
    steps_completed: Optional[int] = Field(
        default=None, description="Number of steps completed before failure"
    )
    last_successful_action: Optional[str] = Field(
        default=None, description="Last action that succeeded"
    )


class BrowserResultData(BaseModel):
    """
    Typed result data from browser agent.
    """

    files: Optional[List[str]] = Field(default=None, description="Downloaded files")
    output: Optional[Union[str, dict[str, Any]]] = Field(
        default=None, description="Extracted data or content"
    )
    text: Optional[str] = Field(default=None, description="Extracted text")
    url: Optional[str] = Field(default=None, description="Final URL")
    task_complete: Optional[bool] = Field(
        default=None, description="Whether browser task is complete"
    )


class GUIResultData(BaseModel):
    """
    Typed result data from GUI agent.
    """

    steps: Optional[int] = Field(default=None, description="Number of steps taken")
    final_action: Optional[str] = Field(
        default=None, description="Last action performed"
    )
    task_complete: Optional[bool] = Field(
        default=None, description="Whether GUI task is complete"
    )
    final_output: Optional[str] = Field(
        default=None, description="Final output or result"
    )
    text: Optional[str] = Field(default=None, description="Extracted text from screen")


class SystemResultData(BaseModel):
    """
    Typed result data from system agent.
    """

    commands: Optional[List[SystemCommandHistoryEntry]] = Field(
        default=None, description="Commands executed with outputs"
    )
    output: Optional[str] = Field(default=None, description="Final output")
    files: Optional[List[str]] = Field(
        default=None, description="Files created or modified"
    )


AgentResultData = Union[
    BrowserResultData, GUIResultData, SystemResultData, dict[str, Any]
]


class ActionResult(BaseModel):
    """
    Result of an action execution with support for agent handoffs.
    """

    success: bool = Field(description="Whether the action succeeded")
    action_taken: str = Field(
        description="Description of the action that was performed"
    )
    method_used: str = Field(
        description="Method used to execute the action (accessibility, cv, ocr, vision, system, process, multi_tier_gui, etc.)"
    )
    confidence: float = Field(
        description="Confidence in the action success (0.0-1.0)", ge=0.0, le=1.0
    )
    error: Optional[str] = Field(
        default=None, description="Error message if action failed"
    )
    screenshot_after: Optional[str] = Field(
        default=None, description="Base64 encoded screenshot after action (optional)"
    )
    data: Optional[AgentResultData] = Field(
        default=None, description="Typed data from action execution"
    )
    handoff_requested: bool = Field(
        default=False,
        description="Whether this agent requests to hand off to another agent",
    )
    suggested_agent: Optional[Literal["gui", "system", "browser"]] = Field(
        default=None, description="Which agent should take over (if handoff requested)"
    )
    handoff_reason: Optional[str] = Field(
        default=None, description="Why the handoff is needed"
    )
    handoff_context: Optional[HandoffContext] = Field(
        default=None,
        description="Typed context about what was attempted and what needs to be done",
    )


class SystemCommand(BaseModel):
    """
    Structured command for system operations.
    """

    command: str = Field(description="Shell command to execute")
    is_destructive: bool = Field(
        description="Whether this command modifies or deletes data"
    )
    requires_confirmation: bool = Field(
        description="Whether user confirmation is needed"
    )
    expected_outcome: str = Field(
        description="What the command is expected to accomplish"
    )
    working_directory: Optional[str] = Field(
        default=None, description="Directory to execute command in"
    )
