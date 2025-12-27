"""CrewAI GUI-agent delegation bridge for Browser-Use.

This module provides a small adapter that allows Browser-Use tools to invoke the
existing CrewAI-configured GUI specialist agent (the one defined in agents.yaml)
and then return control back to the Browser-Use run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from crewai import Agent, Crew, Process, Task


@dataclass(frozen=True)
class GuiDelegationResult:
    """Result of a GUI delegation call."""

    success: bool
    output: str


class CrewGuiDelegate:
    """Runs a one-off CrewAI subtask using the GUI specialist agent."""

    def __init__(
        self,
        agents_config: Dict[str, Any],
        tool_map: Dict[str, Any],
        platform_context: str,
        gui_llm: Any,
    ) -> None:
        self._agents_config = agents_config
        self._tool_map = tool_map
        self._platform_context = platform_context
        self._gui_llm = gui_llm

    def run_os_dialog_task(self, task: str) -> GuiDelegationResult:
        """Run a GUI-only subtask focused on OS-native dialogs.

        Args:
            task: Natural language task for handling the OS dialog.

        Returns:
            GuiDelegationResult
        """
        agent = self._create_gui_agent()

        wrapped_task = (
            "You are handling an OS-native dialog that appeared during a browser automation run.\n"
            "You MUST only interact with OS-level dialogs (file picker, permission prompt).\n"
            "Do NOT interact with the webpage itself.\n\n"
            f"OS DIALOG GOAL: {task}\n"
        )

        crew_task = Task(
            description=wrapped_task,
            expected_output=(
                "Return a short confirmation of what you did and what changed on screen. "
                "If you could not find the dialog or could not complete it, clearly explain why."
            ),
        )

        crew = Crew(
            agents=[agent],
            tasks=[crew_task],
            process=Process.sequential,
            verbose=False,
        )

        try:
            result = crew.kickoff()
            output = str(result)
            success = (
                "could not" not in output.lower() and "failed" not in output.lower()
            )
            return GuiDelegationResult(success=success, output=output)
        except KeyboardInterrupt:
            return GuiDelegationResult(success=False, output="Task cancelled by user")

    def _create_gui_agent(self) -> Agent:
        """Create the CrewAI GUI specialist agent from config."""
        config = self._agents_config["gui_agent"]
        tool_names: List[str] = config.get("tools", [])
        tools = [self._tool_map[name] for name in tool_names if name in self._tool_map]

        backstory_with_context = config["backstory"] + self._platform_context

        def step_callback(step_output):
            from ..crew import ComputerUseCrew

            if ComputerUseCrew.is_cancelled():
                raise KeyboardInterrupt("Task cancelled by user")

        return Agent(
            role=config["role"],
            goal=config["goal"],
            backstory=backstory_with_context,
            verbose=False,
            llm=self._gui_llm,
            max_iter=config.get("max_iter", 25),
            allow_delegation=config.get("allow_delegation", False),
            memory=True,
            tools=tools,
            step_callback=step_callback,
        )
