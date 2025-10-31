"""
CrewAI crew configuration for computer use automation.
"""

from pathlib import Path
from crewai import Agent
from .config.llm_config import LLMConfig
from .agents.coordinator import CoordinatorAgent
from .agents.gui_agent import GUIAgent
from .agents.browser_agent import BrowserAgent
from .agents.system_agent import SystemAgent
from .utils.coordinate_validator import CoordinateValidator
from .tools.platform_registry import PlatformToolRegistry
from .schemas.actions import ActionResult
from .schemas.browser_output import BrowserOutput
from .utils.ui import (
    print_task_analysis,
    print_agent_start,
    print_success,
    print_failure,
    print_handoff,
    print_warning,
    print_info,
)
import yaml


class ComputerUseCrew:
    """
    Computer use automation crew with specialized agents.
    Orchestrates all agents using CrewAI framework.
    """

    def __init__(
        self,
        capabilities,
        safety_checker,
        llm_client=None,
        vision_llm_client=None,
        browser_llm_client=None,
        confirmation_manager=None,
        twilio_service=None,
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
            twilio_service: Optional TwilioService instance for phone verification
        """
        self.capabilities = capabilities
        self.safety_checker = safety_checker
        self.confirmation_manager = confirmation_manager

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
            twilio_service=twilio_service,
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
        self.coordinator_agent = CoordinatorAgent(self.llm)
        self.gui_agent = GUIAgent(self.tool_registry, self.vision_llm)
        self.browser_agent = BrowserAgent(self.tool_registry)
        self.system_agent = SystemAgent(
            self.tool_registry, self.safety_checker, self.llm
        )

    def _create_crew(self):
        """
        CrewAI Crew orchestration is managed directly via execute_task method.

        The execute_task method analyzes tasks and delegates to specialized agents
        (Coordinator, Browser, GUI, System) based on task requirements.

        This provides more flexibility than using CrewAI's built-in task delegation,
        as we need dynamic routing based on task analysis results.

        Returns:
            None (crew delegation handled manually)
        """
        # Not creating a Crew instance since we manage delegation manually
        return None

    def create_coordinator_agent(self) -> Agent:
        """
        Create coordinator agent for task analysis.
        """
        config = self.agents_config["coordinator"]

        return Agent(
            role=config["role"],
            goal=config["goal"],
            backstory=config["backstory"],
            verbose=config.get("verbose", True),
            llm=self.llm,
            allow_delegation=True,
        )

    def create_gui_agent_wrapper(self) -> Agent:
        """
        Create CrewAI agent wrapper for GUI agent.
        """
        config = self.agents_config["gui_agent"]

        return Agent(
            role=config["role"],
            goal=config["goal"],
            backstory=config["backstory"],
            verbose=config.get("verbose", True),
            llm=self.vision_llm,
        )

    def create_browser_agent_wrapper(self) -> Agent:
        """
        Create CrewAI agent wrapper for browser agent.
        """
        config = self.agents_config["browser_agent"]

        return Agent(
            role=config["role"],
            goal=config["goal"],
            backstory=config["backstory"],
            verbose=config.get("verbose", True),
            llm=self.llm,
        )

    def create_system_agent_wrapper(self) -> Agent:
        """
        Create CrewAI agent wrapper for system agent.
        """
        config = self.agents_config["system_agent"]

        return Agent(
            role=config["role"],
            goal=config["goal"],
            backstory=config["backstory"],
            verbose=config.get("verbose", True),
            llm=self.llm,
        )

    async def execute_task(self, task: str) -> dict:
        """
        Execute task with sequential agent coordination and data passing.
        Agents execute in order with context from previous agents.

        Args:
            task: Natural language task description

        Returns:
            Result dictionary with execution details
        """
        analysis = await self.coordinator_agent.analyze_task(task)
        print_task_analysis(task, analysis)

        if analysis.direct_response:
            from .utils.ui import console

            console.print()
            console.print(f"[cyan]🤖 {analysis.direct_response}[/cyan]")
            console.print()
            return self._build_result(task, analysis, [], True)

        results = []
        context = {"task": task, "previous_results": []}

        if analysis.requires_browser:
            print_agent_start("BROWSER")
            browser_task = (
                analysis.browser_subtask.objective if analysis.browser_subtask else task
            )
            if analysis.browser_subtask:
                context["expected_output"] = analysis.browser_subtask.expected_output
                print_info(f"📋 Sub-task: {browser_task}")
                print_info(f"📦 Expected: {analysis.browser_subtask.expected_output}")

            result = await self._execute_browser(browser_task, context)
            results.append(result)
            context["previous_results"].append(result.model_dump())

            browser_completed_attempt = (
                result.data.get("task_complete", False) if result.data else False
            )

            if result.success:
                print_success("Browser task completed successfully")

                if browser_completed_attempt and not (
                    analysis.requires_gui or analysis.requires_system
                ):
                    print_success("Task fully completed by Browser agent")
                    return self._build_result(task, analysis, results, True)
            elif browser_completed_attempt:
                print_warning(
                    "Browser agent called done() but failed - cannot proceed to next agent"
                )
                if result.data and "output" in result.data:
                    output_data = result.data["output"]
                    if isinstance(output_data, dict):
                        try:
                            browser_output = BrowserOutput(**output_data)
                            print_info(f"Browser says: {browser_output.text}")
                            if browser_output.has_files():
                                print_info(
                                    f"Files available: {browser_output.get_file_count()} file(s)"
                                )
                                for file_path in browser_output.files[:3]:
                                    console.print(f"  [dim]• {file_path}[/dim]")
                        except Exception:
                            print_info(f"Output: {output_data}")
                    else:
                        print_info(f"Output: {output_data}")

                if analysis.requires_gui or analysis.requires_system:
                    print_failure(
                        "Subsequent agents require browser output - task cannot continue"
                    )
                return self._build_result(task, analysis, results, False)
            else:
                print_failure(f"Browser task failed: {result.error or 'Unknown error'}")
                return self._build_result(task, analysis, results, False)

        if analysis.requires_gui:
            print_agent_start("GUI")
            gui_task = analysis.gui_subtask.objective if analysis.gui_subtask else task
            if analysis.gui_subtask:
                context["expected_output"] = analysis.gui_subtask.expected_output
                print_info(f"📋 Sub-task: {gui_task}")
                print_info(f"📦 Expected: {analysis.gui_subtask.expected_output}")

            result = await self._execute_gui(gui_task, context)
            results.append(result)
            context["previous_results"].append(result.model_dump())

            if result.handoff_requested:
                suggested = result.suggested_agent
                print_handoff(
                    "GUI",
                    suggested.upper() if suggested else "UNKNOWN",
                    result.handoff_reason,
                )

                context["handoff_context"] = result.handoff_context

                if suggested == "system":
                    print_agent_start("SYSTEM (Handoff)")
                    handoff_result = await self._execute_system(task, context)
                    results.append(handoff_result)

                    if handoff_result.success:
                        print_success("System agent completed handoff task")
                        context["handoff_succeeded"] = True
                    else:
                        print_failure(
                            f"System agent also failed: {handoff_result.error}"
                        )
                        return self._build_result(task, analysis, results, False)
                elif suggested == "browser":
                    print_agent_start("BROWSER (Handoff)")
                    handoff_result = await self._execute_browser(task, context)
                    results.append(handoff_result)

                    if handoff_result.success:
                        print_success("Browser agent completed handoff task")
                        context["handoff_succeeded"] = True
                    else:
                        print_failure(
                            f"Browser agent also failed: {handoff_result.error}"
                        )
                        return self._build_result(task, analysis, results, False)
            elif result.success:
                print_success("GUI task completed")

                if result.data and result.data.get("task_complete"):
                    print_success(
                        "Task fully completed by GUI agent - skipping System agent"
                    )
                    return self._build_result(task, analysis, results, True)
            else:
                if not context.get("handoff_succeeded"):
                    print_failure(f"GUI task failed: {result.error or 'Unknown error'}")
                    return self._build_result(task, analysis, results, False)

        if analysis.requires_system and not context.get("task_complete"):
            print_agent_start("SYSTEM")
            system_task = (
                analysis.system_subtask.objective if analysis.system_subtask else task
            )
            if analysis.system_subtask:
                context["expected_output"] = analysis.system_subtask.expected_output
                print_info(f"📋 Sub-task: {system_task}")
                print_info(f"📦 Expected: {analysis.system_subtask.expected_output}")

            result = await self._execute_system(system_task, context)
            results.append(result)

            if result.handoff_requested:
                suggested = result.suggested_agent
                print_handoff(
                    "SYSTEM",
                    suggested.upper() if suggested else "UNKNOWN",
                    result.handoff_reason,
                )

                context["handoff_context"] = result.handoff_context

                if suggested == "gui":
                    print_agent_start("GUI (Handoff)")
                    handoff_result = await self._execute_gui(task, context)
                    results.append(handoff_result)

                    if handoff_result.success:
                        print_success("GUI agent completed handoff task")
                        context["handoff_succeeded"] = True
                    else:
                        print_failure(f"GUI agent also failed: {handoff_result.error}")
                        return self._build_result(task, analysis, results, False)
                elif suggested == "browser":
                    print_agent_start("BROWSER (Handoff)")
                    handoff_result = await self._execute_browser(task, context)
                    results.append(handoff_result)

                    if handoff_result.success:
                        print_success("Browser agent completed handoff task")
                        context["handoff_succeeded"] = True
                    else:
                        print_failure(
                            f"Browser agent also failed: {handoff_result.error}"
                        )
                        return self._build_result(task, analysis, results, False)
            elif result.success:
                print_success("System task completed")
            else:
                if not context.get("handoff_succeeded"):
                    print_failure(
                        f"System task failed: {result.error or 'Unknown error'}"
                    )
                    return self._build_result(task, analysis, results, False)

        overall_success = all(r.success for r in results)

        self._print_header("TASK COMPLETE" if overall_success else "TASK FAILED")
        if overall_success:
            print(f"  ✅ All {len(results)} agent(s) completed successfully\n")
        else:
            print(f"  ❌ Task failed after {len(results)} step(s)\n")

        return self._build_result(task, analysis, results, overall_success)

    async def _execute_browser(self, task: str, context: dict) -> ActionResult:
        """
        Execute browser agent with loop until completion.
        Browser-Use handles internal looping automatically.
        Returns ActionResult (typed).
        """
        print("  🔄 Browser-Use agent started (runs until task complete)...")
        return await self.browser_agent.execute_task(task, context=context)

    async def _execute_gui(self, task: str, context: dict) -> ActionResult:
        """
        Execute GUI agent with multi-step planning.
        GUI agent handles its own step loop.
        Returns ActionResult (typed).
        """
        return await self.gui_agent.execute_task(task, context=context)

    async def _execute_system(self, task: str, context: dict) -> ActionResult:
        """
        Execute system agent with context from previous agents.
        Passes confirmation manager for command approval.
        Returns ActionResult (typed).
        """
        context["confirmation_manager"] = self.confirmation_manager
        return await self.system_agent.execute_task(task, context)

    def _print_header(self, text: str):
        """Print styled header."""
        width = 60
        print(f"\n{'=' * width}")
        print(f"  {text}")
        print(f"{'=' * width}\n")

    def _print_section(self, text: str):
        """Print styled section."""
        print(f"{'─' * 60}")
        print(f"  {text}")
        print(f"{'─' * 60}\n")

    def _build_result(self, task: str, analysis, results: list, success: bool) -> dict:
        """Build final result dictionary."""
        return {
            "task": task,
            "analysis": analysis.dict(),
            "results": [r.model_dump() for r in results],
            "overall_success": success,
        }
