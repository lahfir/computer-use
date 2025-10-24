"""
Action schemas for different agent types.
"""

from typing import Optional, List, Literal
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
    data: Optional[dict] = Field(
        default=None, description="Additional data from action execution"
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
    handoff_context: Optional[dict] = Field(
        default=None,
        description="Context about what was attempted and what needs to be done",
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
