"""
State management for the UI: Dataclasses and activity tracking.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class VerbosityLevel(Enum):
    """Verbosity levels for UI output."""

    QUIET = 0
    NORMAL = 1
    VERBOSE = 2


class ActionType(Enum):
    """Types of actions for visual distinction."""

    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    OPEN = "open"
    READ = "read"
    SEARCH = "search"
    NAVIGATE = "navigate"
    ANALYZE = "analyze"
    EXECUTE = "execute"
    PLAN = "plan"
    COMPLETE = "complete"
    ERROR = "error"
    WEBHOOK = "webhook"


@dataclass
class ToolState:
    """State of a single tool execution."""

    tool_id: str
    name: str
    status: Literal["pending", "running", "success", "error"] = "pending"
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Any] = None
    error: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: float = 0.0

    def complete(self, success: bool, output: Any = None, error: str = None):
        self.status = "success" if success else "error"
        self.output_data = output
        self.error = error
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time


@dataclass
class AgentState:
    """State of an agent."""

    agent_id: str
    name: str
    status: Literal["idle", "thinking", "executing", "complete", "error"] = "idle"
    current_thought: Optional[str] = None
    tools: List[ToolState] = field(default_factory=list)
    active_tool_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def duration(self) -> float:
        """Calculate agent's active duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def add_tool(self, name: str, input_data: Any) -> ToolState:
        tool_id = str(uuid.uuid4())
        tool = ToolState(
            tool_id=tool_id,
            name=name,
            input_data=(
                input_data if isinstance(input_data, dict) else {"value": input_data}
            ),
        )
        self.tools.append(tool)
        self.active_tool_id = tool_id
        self.status = "executing"
        return tool

    def get_tool(self, tool_id: str) -> Optional[ToolState]:
        for tool in self.tools:
            if tool.tool_id == tool_id:
                return tool
        return None

    def get_active_tool(self) -> Optional[ToolState]:
        if not self.active_tool_id:
            return None
        return self.get_tool(self.active_tool_id)


@dataclass
class TaskState:
    """Global state of the current task."""

    task_id: str
    description: str
    status: Literal["pending", "running", "complete", "error"] = "pending"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    agents: Dict[str, AgentState] = field(default_factory=dict)
    active_agent_id: Optional[str] = None
    token_input: int = 0
    token_output: int = 0
    total_tools: int = 0
    failed_tools: int = 0

    def get_agent(self, name: str) -> AgentState:
        # Check if agent exists by name
        for agent in self.agents.values():
            if agent.name == name:
                return agent

        # Create new agent if not found
        agent_id = str(uuid.uuid4())
        agent = AgentState(agent_id=agent_id, name=name)
        self.agents[agent_id] = agent
        return agent

    def set_active_agent(self, name: str) -> AgentState:
        agent = self.get_agent(name)

        # Set previous active agent to idle
        if self.active_agent_id and self.active_agent_id != agent.agent_id:
            prev_agent = self.agents.get(self.active_agent_id)
            if prev_agent and prev_agent.status != "complete":
                prev_agent.status = "idle"

        self.active_agent_id = agent.agent_id
        if agent.status == "idle":
            agent.status = "thinking"
        return agent

    @property
    def duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
