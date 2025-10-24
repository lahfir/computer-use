"""
Workflow planning schemas for intelligent task decomposition.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from .actions import AgentResultData


AgentType = Literal["browser", "gui", "system"]


class AgentResult(BaseModel):
    """
    Result from a single agent execution.
    Includes minimal handoff info so coordinator can see handoff requests.
    """

    agent: AgentType = Field(description="Agent type that executed")
    subtask: str = Field(description="Subtask that was executed")
    success: bool = Field(description="Whether execution succeeded")
    data: Optional[AgentResultData] = Field(
        default=None, description="Typed result data from agent"
    )
    error: Optional[str] = Field(default=None, description="Error if failed")
    handoff_requested: bool = Field(
        default=False, description="Whether agent requested handoff"
    )
    suggested_agent: Optional[AgentType] = Field(
        default=None, description="Agent suggested for handoff"
    )
    handoff_reason: Optional[str] = Field(
        default=None, description="Why handoff was requested"
    )


class WorkflowContext(BaseModel):
    """
    Shared context across agent handoffs.
    """

    original_task: str = Field(description="Original user task")
    agent_results: List[AgentResult] = Field(
        default_factory=list, description="Results from previous agents"
    )
    completed: bool = Field(default=False, description="Whether task is complete")


class CoordinatorDecision(BaseModel):
    """
    Decision from coordinator about next action.
    """

    agent: AgentType = Field(description="Which agent to use")
    subtask: str = Field(description="Specific task for this agent")
    reasoning: str = Field(description="Why this agent and subtask")
    is_complete: bool = Field(default=False, description="Is the entire task complete?")


class WorkflowResult(BaseModel):
    """
    Final result from workflow execution.
    """

    success: bool = Field(description="Whether task completed successfully")
    iterations: int = Field(description="Number of iterations taken")
    agents_used: List[AgentType] = Field(description="List of agent types used")
    results: List[AgentResult] = Field(description="Results from each agent")


class ResourceRequirement(BaseModel):
    """
    A resource needed to complete the task.
    """

    resource_type: str = Field(
        description="Type of resource: 'application', 'website', 'file', or 'service'"
    )
    name: str = Field(
        description="Name of the resource (e.g., 'Calculator.app', 'Google Chrome', 'design_file.png')"
    )
    purpose: str = Field(description="Why this resource is needed for the task")


class TaskUnderstanding(BaseModel):
    """
    Deep understanding of user intent.
    Result of analyzing user request to determine what they really want.
    """

    intent: str = Field(description="What user ultimately wants to achieve")
    required_steps: List[str] = Field(description="Logical breakdown of steps needed")
    success_criteria: str = Field(description="How we know task is complete")
    potential_challenges: List[str] = Field(
        default_factory=list, description="What might go wrong or block progress"
    )
    resource_requirements: List[ResourceRequirement] = Field(
        default_factory=list,
        description="Resources needed to complete the task (apps, websites, files)",
    )


class WorkflowStep(BaseModel):
    """
    Single step in workflow execution plan.
    Defines what one agent should accomplish.
    """

    step_id: str = Field(description="Unique identifier for this step")
    agent_type: str = Field(
        description="Which agent handles this: 'browser', 'gui', or 'system'"
    )
    role: str = Field(description="What this agent should accomplish")
    instructions: str = Field(description="Detailed instructions for the agent")
    expected_output: str = Field(description="What output we expect from this step")
    depends_on: List[str] = Field(
        default_factory=list, description="IDs of previous steps this depends on"
    )


class WorkflowPlan(BaseModel):
    """
    Complete workflow execution plan.
    Breaks down user request into sequential agent tasks.
    """

    steps: List[WorkflowStep] = Field(description="Ordered list of workflow steps")
    estimated_duration: str = Field(
        default="unknown", description="Estimated time to complete"
    )
    critical_resources: List[str] = Field(
        default_factory=list, description="Key resources needed for success"
    )
