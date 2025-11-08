"""CrewAI-based multi-agent computer automation system."""

from pathlib import Path
from typing import Optional, Dict, List, Any
from crewai import Agent, Task, Crew, Process
from .config.llm_config import LLMConfig
from .agents.gui_agent import GUIAgent
from .agents.browser_agent import BrowserAgent
from .agents.system_agent import SystemAgent
from .schemas import TaskCompletionOutput, TaskExecutionResult
from .crew_tools import (
    TakeScreenshotTool,
    ClickElementTool,
    TypeTextTool,
    OpenApplicationTool,
    ReadScreenTextTool,
    GetAppTextTool,
    ScrollTool,
    ListRunningAppsTool,
    CheckAppRunningTool,
    GetAccessibleElementsTool,
    GetWindowImageTool,
    WebAutomationTool,
    ExecuteShellCommandTool,
    FindApplicationTool,
    RequestHumanInputTool,
)
from .utils.coordinate_validator import CoordinateValidator
from .tools.platform_registry import PlatformToolRegistry
from .utils.ui import print_success, print_failure, print_info
import yaml
import asyncio
import platform


class ComputerUseCrew:
    """
    CrewAI-powered computer automation system.
    Uses CrewAI's Agent, Task, and Crew for proper multi-agent orchestration.
    """

    def __init__(
        self,
        capabilities: Any,
        safety_checker: Any,
        llm_client: Optional[Any] = None,
        vision_llm_client: Optional[Any] = None,
        browser_llm_client: Optional[Any] = None,
        confirmation_manager: Optional[Any] = None,
        twilio_service: Optional[Any] = None,
    ) -> None:
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

        self.llm = llm_client or LLMConfig.get_llm()
        self.vision_llm = vision_llm_client or LLMConfig.get_vision_llm()
        self.browser_llm = browser_llm_client or LLMConfig.get_browser_llm()

        self.agents_config = self._load_yaml_config("agents.yaml")
        self.tasks_config = self._load_yaml_config("tasks.yaml")

        self.tool_registry = self._initialize_tool_registry(twilio_service)
        self._initialize_legacy_agents()

        self.gui_tools = self._initialize_gui_tools()
        self.web_automation_tool = self._initialize_web_tool()
        self.execute_command_tool = self._initialize_system_tool()

        self.crew: Optional[Crew] = None
        self.platform_context = self._get_platform_context()

    def _get_platform_context(self) -> str:
        """
        Get platform information for agent context.

        Returns:
            Formatted platform context string
        """
        os_name = platform.system()
        os_version = platform.release()
        machine = platform.machine()

        if os_name == "Darwin":
            platform_name = "macOS"
        elif os_name == "Windows":
            platform_name = "Windows"
        elif os_name == "Linux":
            platform_name = "Linux"
        else:
            platform_name = os_name

        context = f"\n\n🖥️  PLATFORM: {platform_name} {os_version} ({machine})\n"

        return context

    def _load_yaml_config(self, filename: str) -> Dict[str, Any]:
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

    def _initialize_tool_registry(
        self, twilio_service: Optional[Any]
    ) -> PlatformToolRegistry:
        """
        Initialize platform tool registry.

        Args:
            twilio_service: Optional TwilioService instance

        Returns:
            Configured PlatformToolRegistry
        """
        coordinate_validator = CoordinateValidator(
            self.capabilities.screen_resolution[0],
            self.capabilities.screen_resolution[1],
        )

        return PlatformToolRegistry(
            self.capabilities,
            safety_checker=self.safety_checker,
            coordinate_validator=coordinate_validator,
            llm_client=self.browser_llm,
            twilio_service=twilio_service,
        )

    def _initialize_legacy_agents(self) -> None:
        """Initialize legacy agent instances for internal use."""
        self.browser_agent_instance = BrowserAgent(self.tool_registry)
        self.gui_agent_instance = GUIAgent(self.tool_registry, self.vision_llm)
        self.system_agent_instance = SystemAgent(
            self.tool_registry, self.safety_checker, self.llm
        )

    def _initialize_gui_tools(self) -> Dict[str, Any]:
        """
        Initialize and configure GUI automation tools.

        Returns:
            Dictionary mapping tool names to configured tool instances
        """
        tools = {
            "take_screenshot": TakeScreenshotTool(),
            "click_element": ClickElementTool(),
            "type_text": TypeTextTool(),
            "open_application": OpenApplicationTool(),
            "read_screen_text": ReadScreenTextTool(),
            "get_app_text": GetAppTextTool(),
            "scroll": ScrollTool(),
            "list_running_apps": ListRunningAppsTool(),
            "check_app_running": CheckAppRunningTool(),
            "get_accessible_elements": GetAccessibleElementsTool(),
            "get_window_image": GetWindowImageTool(),
            "find_application": FindApplicationTool(),
            "request_human_input": RequestHumanInputTool(),
        }

        for tool in tools.values():
            tool._tool_registry = self.tool_registry

        tools["find_application"]._llm = LLMConfig.get_orchestration_llm()

        return tools

    def _initialize_web_tool(self) -> WebAutomationTool:
        """
        Initialize and configure web automation tool.

        Returns:
            Configured WebAutomationTool instance
        """
        tool = WebAutomationTool()
        tool._tool_registry = self.tool_registry
        return tool

    def _initialize_system_tool(self) -> ExecuteShellCommandTool:
        """
        Initialize and configure system command execution tool.

        Returns:
            Configured ExecuteShellCommandTool instance
        """
        tool = ExecuteShellCommandTool()
        tool._safety_checker = self.safety_checker
        tool._confirmation_manager = self.confirmation_manager
        return tool

    def _build_tool_map(self) -> Dict[str, Any]:
        """
        Build mapping of tool names to tool instances.

        Returns:
            Dictionary mapping tool names to instances
        """
        return {
            "web_automation": self.web_automation_tool,
            **self.gui_tools,
            "execute_shell_command": self.execute_command_tool,
        }

    def _create_agent(
        self,
        config_key: str,
        tool_names: List[str],
        llm: Any,
        tool_map: Dict[str, Any],
        is_manager: bool = False,
    ) -> Agent:
        """
        Create a CrewAI agent from configuration.

        Args:
            config_key: Key in agents_config for this agent
            tool_names: List of tool names to assign
            llm: LLM instance for this agent
            tool_map: Mapping of tool names to instances
            is_manager: Whether this is a manager agent

        Returns:
            Configured Agent instance
        """
        config = self.agents_config[config_key]
        tools = [tool_map[name] for name in tool_names if name in tool_map]

        backstory_with_context = config["backstory"] + self.platform_context

        agent_params = {
            "role": config["role"],
            "goal": config["goal"],
            "backstory": backstory_with_context,
            "verbose": config.get("verbose", True),
            "llm": llm,
            "max_iter": config.get("max_iter", 15),
            "allow_delegation": config.get("allow_delegation", False),
            "memory": True,
        }

        if not is_manager:
            agent_params["tools"] = tools
            agent_params["output_pydantic"] = TaskCompletionOutput

        return Agent(**agent_params)

    def _create_crewai_agents(self) -> Dict[str, Agent]:
        """
        Create CrewAI Agent instances from YAML configs.

        Returns:
            Dictionary of agent_name -> Agent instance
        """
        tool_map = self._build_tool_map()

        manager_agent = self._create_agent(
            "manager", [], self.llm, tool_map, is_manager=True
        )

        browser_tools = self.agents_config["browser_agent"].get("tools", [])
        gui_tools = self.agents_config["gui_agent"].get("tools", [])
        system_tools = self.agents_config["system_agent"].get("tools", [])

        browser_agent = self._create_agent(
            "browser_agent", browser_tools, self.llm, tool_map
        )
        gui_agent = self._create_agent(
            "gui_agent", gui_tools, self.vision_llm, tool_map
        )
        system_agent = self._create_agent(
            "system_agent", system_tools, self.llm, tool_map
        )

        return {
            "manager": manager_agent,
            "browser_agent": browser_agent,
            "gui_agent": gui_agent,
            "system_agent": system_agent,
        }

    def _extract_context_from_history(
        self, conversation_history: List[Dict[str, Any]]
    ) -> str:
        """
        Extract context string from conversation history.

        Args:
            conversation_history: List of previous interactions

        Returns:
            Formatted context string
        """
        if not conversation_history:
            return ""

        last_interaction = conversation_history[-1]
        if "result" not in last_interaction or not last_interaction["result"]:
            return ""

        result_data = last_interaction["result"]
        if isinstance(result_data, dict) and "result" in result_data:
            return f"\n\nPREVIOUS TASK OUTPUT:\n{result_data['result']}\n"

        return ""

    async def execute_task(
        self,
        task: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskExecutionResult:
        """
        Execute task using CrewAI's intelligent multi-agent orchestration.
        Uses intelligent task decomposition to create optimal execution plan.

        Args:
            task: Natural language task description
            conversation_history: List of previous messages

        Returns:
            TaskExecutionResult with execution details
        """
        if conversation_history is None:
            conversation_history = []

        try:
            from langchain_core.messages import HumanMessage
            from pydantic import BaseModel, Field
            from typing import List as TypingList

            context_str = self._extract_context_from_history(conversation_history)
            agents_dict = self._create_crewai_agents()

            class SubTask(BaseModel):
                agent_type: str = Field(
                    description="Agent type: 'browser', 'gui', or 'system'"
                )
                description: str = Field(
                    description="Clear, specific task description for this agent"
                )
                expected_output: str = Field(
                    description="What this agent should produce"
                )
                depends_on_previous: bool = Field(
                    description="True if this subtask needs output from previous subtask"
                )

            class TaskPlan(BaseModel):
                reasoning: str = Field(
                    description="Analysis of the task and orchestration strategy"
                )
                subtasks: TypingList[SubTask] = Field(
                    description="List of subtasks in execution order (can be 1 for simple tasks)"
                )

            orchestration_prompt = f"""You are an intelligent task orchestration system. Analyze this user request:

USER REQUEST: {task}

AGENT CAPABILITIES:
- browser: Web research, downloads, data extraction, website interaction
- gui: Desktop applications (TextEdit, Calculator, Notes, Finder, System Settings, ANY GUI app), file creation via apps
- system: Shell commands, file operations via CLI (NOT for system settings/preferences)

🚨 CRITICAL AGENT SELECTION RULES:

GUI AGENT (use for):
- Opening and interacting with ANY desktop application
- System Settings/Preferences changes (theme, display, sound, etc.)
- Calculator, TextEdit, Notes, Finder, etc.
- ANY task that requires clicking buttons or navigating UI
- File creation through GUI apps

SYSTEM AGENT (use for):
- Pure shell commands (ls, cp, mv, find, grep, etc.)
- File operations via CLI (when GUI is not needed)
- Running scripts or command-line tools
- NEVER for system preferences/settings changes

BROWSER AGENT (use for):
- Web research and data extraction
- Downloading files from websites
- Website interaction and automation

CRITICAL ANALYSIS PATTERNS:

"Change system theme/settings/preferences"
→ ONE subtask: gui (open System Settings, navigate, click options)
→ NEVER use system agent for OS settings changes

"Research X and create/save file with results"
→ TWO subtasks: browser (get data) → gui or system (create file with that data)
→ Browser CANNOT create desktop files directly
→ Data must flow from browser → file creator

"Open app and do something"
→ ONE subtask: gui (handles entire app workflow)

"Calculate/compute something in desktop app"
→ ONE subtask: gui (opens app, performs calculation, gets result)

"Download from web"
→ ONE subtask: browser (handles download)

"Create file with specific content"
→ ONE subtask: gui (use TextEdit/Notes) OR system (use echo/cat commands)

"Find file and do something with it"
→ ONE or TWO: depends if finding requires system search or GUI navigation

ORCHESTRATION RULES:
1. If task can be completed by ONE agent → use 1 subtask
2. If task needs data from one source → used by another → use 2+ subtasks with depends_on_previous=True
3. Browser agent outputs can be used by gui/system agents (set depends_on_previous=True)
4. Each subtask must have CLEAR, ACTIONABLE description
5. Expected output must specify EXACTLY what the agent will produce

🚨 CRITICAL FOR BROWSER TASKS:
- Browser agent uses ONE web_automation tool call per subtask
- Be EXTREMELY SPECIFIC about what webpage to visit and what data to extract
- Format: "Go to [exact URL] and extract [exact data]" - NOT "research X" or "find Y"
- Example GOOD: "Navigate to https://finance.yahoo.com/quote/NVDA, extract current stock price and 5-day historical prices into structured format"
- Example BAD: "Research Nvidia stock price" (too vague, agent will hallucinate multiple steps)
- If task needs multiple web actions, create MULTIPLE browser subtasks

Analyze the request and create an optimal task plan:"""

            orchestration_llm = LLMConfig.get_orchestration_llm()
            structured_llm = orchestration_llm.with_structured_output(TaskPlan)
            plan = structured_llm.invoke([HumanMessage(content=orchestration_prompt)])

            print_info(f"🧠 Task Analysis: {plan.reasoning}")
            print_info(f"📋 Execution Plan: {len(plan.subtasks)} subtask(s)")
            for i, subtask in enumerate(plan.subtasks, 1):
                print_info(
                    f"  {i}. {subtask.agent_type}: {subtask.description[:70]}..."
                )

            crew_agents = []
            crew_tasks = []

            for idx, subtask in enumerate(plan.subtasks):
                agent_key = f"{subtask.agent_type}_agent"
                if agent_key not in agents_dict:
                    print_failure(f"⚠️  Invalid agent: {subtask.agent_type}, skipping")
                    continue

                agent = agents_dict[agent_key]
                crew_agents.append(agent)

                task_desc = subtask.description
                if idx == 0 and context_str:
                    task_desc = f"{task_desc}{context_str}"

                crew_task = Task(
                    description=task_desc,
                    expected_output=subtask.expected_output,
                    agent=agent,
                    output_pydantic=TaskCompletionOutput,
                    context=(
                        [crew_tasks[-1]]
                        if subtask.depends_on_previous and crew_tasks
                        else None
                    ),
                )
                crew_tasks.append(crew_task)

            if len(crew_tasks) == 0:
                return TaskExecutionResult(
                    task=task,
                    overall_success=True,
                    result=plan.reasoning
                    or "Hello! I'm ready to help you with computer automation tasks. What would you like me to do?",
                    error=None,
                )

            self.crew = Crew(
                agents=list(set(crew_agents)),
                tasks=crew_tasks,
                process=Process.sequential,
                verbose=True,
            )

            print_success(
                f"🚀 Executing crew with {len(crew_agents)} agent(s) and {len(crew_tasks)} task(s)"
            )

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.crew.kickoff)

            print_success("✅ Crew execution completed!")

            return TaskExecutionResult(
                task=task,
                result=str(result),
                overall_success=True,
            )

        except Exception as e:
            print_failure(f"❌ Crew execution failed: {str(e)}")
            import traceback

            traceback.print_exc()

            return TaskExecutionResult(
                task=task,
                overall_success=False,
                error=str(e),
            )
