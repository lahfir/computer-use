"""
CrewAI-based multi-agent computer automation system.
Properly leverages CrewAI's Agent, Task, and Crew orchestration.
"""

from pathlib import Path
from crewai import Agent, Task, Crew, Process
from .config.llm_config import LLMConfig
from .agents.coordinator import CoordinatorAgent
from .agents.gui_agent import GUIAgent
from .agents.browser_agent import BrowserAgent
from .agents.system_agent import SystemAgent
from .crew_tools import (
    TakeScreenshotTool,
    ClickElementTool,
    TypeTextTool,
    OpenApplicationTool,
    ReadScreenTextTool,
    ScrollTool,
    WebAutomationTool,
    ExecuteShellCommandTool,
    FindApplicationTool,
)
from .utils.coordinate_validator import CoordinateValidator
from .tools.platform_registry import PlatformToolRegistry
from .utils.ui import (
    print_task_analysis,
    print_success,
    print_failure,
    print_info,
    console,
)
import yaml


class ComputerUseCrew:
    """
    CrewAI-powered computer automation system.
    Uses CrewAI's Agent, Task, and Crew for proper multi-agent orchestration.
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
        Initialize CrewAI-based automation system.

        Args:
            capabilities: PlatformCapabilities instance
            safety_checker: SafetyChecker instance
            llm_client: Optional LLM client for regular tasks
            vision_llm_client: Optional LLM client for vision tasks
            browser_llm_client: Optional LLM client for browser automation
            confirmation_manager: CommandConfirmation instance
            twilio_service: Optional TwilioService instance
        """
        self.capabilities = capabilities
        self.safety_checker = safety_checker
        self.confirmation_manager = confirmation_manager

        # LLMs for different agents
        self.llm = llm_client or LLMConfig.get_llm()
        self.vision_llm = vision_llm_client or LLMConfig.get_vision_llm()
        self.browser_llm = browser_llm_client or LLMConfig.get_browser_llm()

        # Load YAML configs
        self.agents_config = self._load_yaml_config("agents.yaml")
        self.tasks_config = self._load_yaml_config("tasks.yaml")

        # Setup tool registry
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

        # Initialize our custom specialized agents (for internal use)
        self.coordinator_agent_instance = CoordinatorAgent(self.llm)
        self.browser_agent_instance = BrowserAgent(self.tool_registry)
        self.gui_agent_instance = GUIAgent(self.tool_registry, self.vision_llm)
        self.system_agent_instance = SystemAgent(
            self.tool_registry, self.safety_checker, self.llm
        )

        self.screenshot_tool = TakeScreenshotTool()
        self.screenshot_tool._tool_registry = self.tool_registry

        self.click_tool = ClickElementTool()
        self.click_tool._tool_registry = self.tool_registry

        self.type_tool = TypeTextTool()
        self.type_tool._tool_registry = self.tool_registry

        self.open_app_tool = OpenApplicationTool()
        self.open_app_tool._tool_registry = self.tool_registry

        self.read_screen_tool = ReadScreenTextTool()
        self.read_screen_tool._tool_registry = self.tool_registry

        self.scroll_tool = ScrollTool()
        self.scroll_tool._tool_registry = self.tool_registry

        self.find_app_tool = FindApplicationTool()
        self.find_app_tool._tool_registry = self.tool_registry
        self.find_app_tool._llm = self.llm

        # Web Automation Tool
        self.web_automation_tool = WebAutomationTool()
        self.web_automation_tool._tool_registry = self.tool_registry

        # System Tool
        self.execute_command_tool = ExecuteShellCommandTool()
        self.execute_command_tool._safety_checker = safety_checker
        self.execute_command_tool._confirmation_manager = confirmation_manager

        # CrewAI agents and crew will be created per-task
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

    def _create_crewai_agents(self) -> dict:
        """
        Create CrewAI Agent instances from YAML configs.

        Returns:
            Dictionary of agent_name -> Agent instance
        """
        agents = {}

        # Coordinator agent (uses our custom CoordinatorAgent internally)
        coord_config = self.agents_config["coordinator"]
        agents["coordinator"] = Agent(
            role=coord_config["role"],
            goal=coord_config["goal"],
            backstory=coord_config["backstory"],
            verbose=coord_config.get("verbose", True),
            llm=self.llm,
            allow_delegation=True,
            max_iter=coord_config.get("max_iter", 1),
        )

        tool_map = {
            "web_automation": self.web_automation_tool,
            "take_screenshot": self.screenshot_tool,
            "click_element": self.click_tool,
            "type_text": self.type_tool,
            "open_application": self.open_app_tool,
            "read_screen_text": self.read_screen_tool,
            "scroll": self.scroll_tool,
            "find_application": self.find_app_tool,
            "execute_shell_command": self.execute_command_tool,
        }

        # Browser agent with web automation
        browser_config = self.agents_config["browser_agent"]
        browser_tools = [
            tool_map[tool_name]
            for tool_name in browser_config.get("tools", [])
            if tool_name in tool_map
        ]

        print(f"🔧 Browser agent tools: {[t.name for t in browser_tools]}")

        agents["browser_agent"] = Agent(
            role=browser_config["role"],
            goal=browser_config["goal"],
            backstory=browser_config["backstory"],
            verbose=browser_config.get("verbose", True),
            llm=self.llm,
            tools=browser_tools,
            max_iter=browser_config.get("max_iter", 20),
            allow_delegation=False,
        )

        # GUI agent with granular desktop automation tools
        gui_config = self.agents_config["gui_agent"]
        gui_tools = [
            tool_map[tool_name]
            for tool_name in gui_config.get("tools", [])
            if tool_name in tool_map
        ]
        agents["gui_agent"] = Agent(
            role=gui_config["role"],
            goal=gui_config["goal"],
            backstory=gui_config["backstory"],
            verbose=gui_config.get("verbose", True),
            llm=self.vision_llm,
            tools=gui_tools,
            max_iter=gui_config.get("max_iter", 15),
        )

        # System agent with shell command execution
        system_config = self.agents_config["system_agent"]
        system_tools = [
            tool_map[tool_name]
            for tool_name in system_config.get("tools", [])
            if tool_name in tool_map
        ]

        print(f"🔧 System agent tools: {[t.name for t in system_tools]}")

        agents["system_agent"] = Agent(
            role=system_config["role"],
            goal=system_config["goal"],
            backstory=system_config["backstory"],
            verbose=system_config.get("verbose", True),
            llm=self.llm,
            tools=system_tools,
            max_iter=system_config.get("max_iter", 10),
            allow_delegation=False,
        )

        return agents

    async def execute_task(self, task: str, conversation_history: list = None) -> dict:
        """
        Execute task using CrewAI orchestration.

        Args:
            task: Natural language task description
            conversation_history: List of previous messages

        Returns:
            Result dictionary with execution details
        """
        if conversation_history is None:
            conversation_history = []

        try:
            # Create CrewAI agents
            agents = self._create_crewai_agents()

            # Analyze task and create tasks
            import asyncio

            analysis_result = await self.coordinator_agent_instance.analyze_task(
                task, conversation_history
            )

            # If direct response, no tasks needed
            if (
                hasattr(analysis_result, "direct_response")
                and analysis_result.direct_response
            ):
                console.print()
                console.print(f"[cyan]🤖 {analysis_result.direct_response}[/cyan]")
                console.print()
                return {
                    "task": task,
                    "overall_success": True,
                    "results": [],
                }

            print_task_analysis(task, analysis_result)

            # Create tasks based on analysis
            tasks = []
            context = {"task": task, "previous_results": []}

            if analysis_result.requires_browser:
                browser_desc = self.tasks_config["browser_task"]["description"].format(
                    browser_subtask=(
                        analysis_result.browser_subtask.objective
                        if analysis_result.browser_subtask
                        else task
                    ),
                    context=str(context),
                )

                browser_task = Task(
                    description=browser_desc,
                    expected_output=self.tasks_config["browser_task"][
                        "expected_output"
                    ],
                    agent=agents["browser_agent"],
                )
                tasks.append(browser_task)

            if analysis_result.requires_gui:
                gui_desc = self.tasks_config["gui_task"]["description"].format(
                    gui_subtask=(
                        analysis_result.gui_subtask.objective
                        if analysis_result.gui_subtask
                        else task
                    ),
                    context=str(context),
                )

                gui_task = Task(
                    description=gui_desc,
                    expected_output=self.tasks_config["gui_task"]["expected_output"],
                    agent=agents["gui_agent"],
                )
                tasks.append(gui_task)

            if analysis_result.requires_system:
                system_desc = self.tasks_config["system_task"]["description"].format(
                    system_subtask=(
                        analysis_result.system_subtask.objective
                        if analysis_result.system_subtask
                        else task
                    ),
                    context=str(context),
                )

                system_task = Task(
                    description=system_desc,
                    expected_output=self.tasks_config["system_task"]["expected_output"],
                    agent=agents["system_agent"],
                )
                tasks.append(system_task)

            # If no tasks, return early
            if not tasks:
                return {
                    "task": task,
                    "overall_success": True,
                    "results": [],
                }

            self.crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                process=Process.sequential,
                verbose=True,
            )

            print_info("🚀 Starting CrewAI crew execution...")
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.crew.kickoff)

            print_success("✅ Crew execution completed!")

            return {
                "task": task,
                "overall_success": True,
                "result": str(result),
            }

        except Exception as e:
            print_failure(f"❌ Crew execution failed: {str(e)}")
            import traceback

            traceback.print_exc()
            return {
                "task": task,
                "overall_success": False,
                "error": str(e),
            }
