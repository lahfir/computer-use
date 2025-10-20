"""
Common response schemas for agents.
"""

from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """
    Standard response format for all agents.
    """

    status: str = Field(
        description="Status of the operation (success, failure, pending)"
    )
    message: str = Field(description="Human-readable message about the result")
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional data from the operation"
    )
    next_action: Optional[str] = Field(
        default=None, description="Suggested next action if task is incomplete"
    )
