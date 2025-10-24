"""
CrewAI crew configuration for computer use automation.
Uses coordinator for intelligent planning, then direct agent execution.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional
from .config.llm_config import LLMConfig
from .agents.coordinator import CoordinatorAgent
from .agents.gui_agent import GUIAgent
from .agents.browser_agent import BrowserAgent
from .agents.system_agent import SystemAgent
from .utils.coordinate_validator import CoordinateValidator
from .tools.platform_registry import PlatformToolRegistry
from .schemas.actions import ActionResult
from .schemas.workflow import WorkflowContext, AgentResult, WorkflowResult
from .utils.ui import console, print_agent_start, print_handoff
import yaml

if TYPE_CHECKING:
    from .utils.platform_detector import PlatformCapabilities
    from .utils.safety_checker import SafetyChecker
    from .utils.command_confirmation import CommandConfirmation
    from .utils.task_stop_handler import TaskStopHandler
    from langchain_core.language_models import BaseChatModel


class ComputerUseCrew:
    """
    Computer use automation crew with specialized agents.
    Orchestrates all agents using CrewAI framework.
    """

    def __init__(
        self,
        capabilities: "PlatformCapabilities",
        safety_checker: "SafetyChecker",
        llm_client: Optional["BaseChatModel"] = None,
        vision_llm_client: Optional["BaseChatModel"] = None,
        browser_llm_client: Optional["BaseChatModel"] = None,
        confirmation_manager: Optional["CommandConfirmation"] = None,
        stop_handler: Optional["TaskStopHandler"] = None,
    ):
        """
        Initialize crew with platform-specific tools.

        Args:
            capabilities: PlatformCapabilities instance
            safety_checker: SafetyChecker instance
            llm_client: Optional LLM client for regular tasks
            vision_llm_client: Optional LLM client for vision tasks
            browser_llm_client: Optional LLM client for browser automation
            confirmation_manager: CommandConfirmation instance for shell command approval
            stop_handler: TaskStopHandler for ESC key handling
        """
        self.capabilities = capabilities
        self.safety_checker = safety_checker
        self.confirmation_manager = confirmation_manager
        self.stop_handler = stop_handler

        # LLMs for different agents
        self.llm = llm_client or LLMConfig.get_llm()
        self.vision_llm = vision_llm_client or LLMConfig.get_vision_llm()
        self.browser_llm = browser_llm_client or LLMConfig.get_browser_llm()

        coordinate_validator = CoordinateValidator(
            capabilities.screen_resolution[0], capabilities.screen_resolution[1]
        )

        self.tool_registry = PlatformToolRegistry(
            capabilities,
            safety_checker=safety_checker,
            coordinate_validator=coordinate_validator,
            llm_client=self.browser_llm,
        )

        self.agents_config = self._load_yaml_config("agents.yaml")
        self.tasks_config = self._load_yaml_config("tasks.yaml")

        self._initialize_specialized_agents()
        # Note: CrewAI Crew is managed directly via execute_task method
        # which delegates to specialized agents based on task analysis
        self.crew = None

    def _load_yaml_config(self, filename: str) -> dict:
        """
        Load YAML configuration file.

        Args:
            filename: Name of YAML file in config directory

        Returns:
            Dictionary with configuration
        """
        config_path = Path(__file__).parent / "config" / filename

        with open(config_path, "r") as f:
            return yaml.safe_load(f)

    def _initialize_specialized_agents(self):
        """
        Initialize all specialized agent instances.
        These handle the actual work.
        """
        # Pass the Pydantic model directly, not a fucking dict!
        self.coordinator_agent = CoordinatorAgent(self.llm, self.capabilities)
        self.gui_agent = GUIAgent(self.tool_registry, self.vision_llm)
        self.browser_agent = BrowserAgent(self.tool_registry)
        self.system_agent = SystemAgent(
            self.tool_registry, self.safety_checker, self.llm
        )

    async def execute_task(self, task: str) -> WorkflowResult:
        """
        Execute task using coordinator for planning, then direct agent execution.

        SIMPLE APPROACH:
        1. Coordinator analyzes and creates workflow plan
        2. Execute each step directly with our agents (no CrewAI complexity)
        3. Pass context between steps manually

        Args:
            task: Natural language task description

        Returns:
            Result dictionary with execution details
        """
        console.print(f"\n[bold]{task}[/bold]")

        agents_map: dict[str, BrowserAgent | GUIAgent | SystemAgent] = {
            "browser": self.browser_agent,
            "gui": self.gui_agent,
            "system": self.system_agent,
        }

        context = WorkflowContext(original_task=task)

        max_iterations = 5
        iteration = 0

        while not context.completed and iteration < max_iterations:
            if self.stop_handler and self.stop_handler.is_stopped():
                console.print(
                    "\n[yellow]⏹️  Task stopped by user (ESC pressed)[/yellow]"
                )
                return WorkflowResult(
                    success=False,
                    iterations=iteration,
                    agents_used=[r.agent for r in context.agent_results],
                    results=context.agent_results,
                )

            iteration += 1

            decision = await self.coordinator_agent.decide_next_action(task, context)

            # Show coordinator decision
            console.print()
            console.print(
                f"[bold magenta]🧠 Coordinator → Step {iteration}[/bold magenta]"
            )
            console.print(
                f"  [cyan]Agent:[/cyan] [bold white]{decision.agent.upper()}[/bold white]"
            )
            console.print(f"  [cyan]Task:[/cyan] {decision.subtask}")
            console.print(f"  [dim]Reasoning: {decision.reasoning}[/dim]")

            if decision.is_complete:
                console.print()
                console.print("[green]━━━ Workflow Complete ━━━[/green]")
                console.print("[green]✓ All tasks finished successfully[/green]")
                context.completed = True
                break

            # Show handoff if switching agents
            if context.agent_results:
                last_agent = context.agent_results[-1].agent
                if last_agent != decision.agent:
                    print_handoff(
                        last_agent.upper(),
                        decision.agent.upper(),
                        f"Switching to {decision.agent} agent for next subtask",
                    )

            # Show agent execution start
            print_agent_start(decision.agent.upper())

            agent = agents_map.get(decision.agent)
            if not agent:
                break

            result: ActionResult = await agent.execute_task(
                decision.subtask, context=context
            )

            # Store lightweight summary in context (NO handoff - that's handled immediately below)
            agent_result = AgentResult(
                agent=decision.agent,
                subtask=decision.subtask,
                success=result.success,
                data=result.data if result.success else None,
                error=result.error if not result.success else None,
            )
            context.agent_results.append(agent_result)

            if not result.success:
                if result.handoff_requested and result.suggested_agent:
                    console.print(
                        f"   [yellow]⚠️  Agent failed, requesting handoff to {result.suggested_agent.upper()}[/yellow]"
                    )
                    console.print(f"   [dim]Reason: {result.handoff_reason}[/dim]")
                else:
                    console.print(f"   [red]✗ {result.error}[/red]")
                    break

        return WorkflowResult(
            success=context.completed,
            iterations=iteration,
            agents_used=[r.agent for r in context.agent_results],
            results=context.agent_results,
        )
