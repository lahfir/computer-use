"""CrewAI-based multi-agent computer automation system."""

import asyncio
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from crewai import Agent, Crew, Process, Task
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from .agents.browser_agent import BrowserAgent
from .agents.coding_agent import CodingAgent
from .config.llm_config import LLMConfig
from .crew_tools import (
    CheckAppRunningTool,
    ClickElementTool,
    CodingAgentTool,
    ExecuteShellCommandTool,
    FindApplicationTool,
    GetAccessibleElementsTool,
    GetWindowImageTool,
    ListRunningAppsTool,
    OpenApplicationTool,
    ReadScreenTextTool,
    RequestHumanInputTool,
    ScrollTool,
    TakeScreenshotTool,
    TypeTextTool,
    WebAutomationTool,
)
from .prompts.orchestration_prompts import get_orchestration_prompt
from .schemas import TaskCompletionOutput, TaskExecutionResult
from .tools.platform_registry import PlatformToolRegistry
from .utils.coordinate_validator import CoordinateValidator
from .utils.ui import (
    ActionType,
    dashboard,
    print_failure,
    print_info,
    print_success,
    print_warning,
)


class SubTask(BaseModel):
    """Structured subtask returned by the orchestration LLM."""

    agent_type: str = Field(
        description="Agent type: 'browser', 'gui', 'system', or 'coding'"
    )
    description: str = Field(
        description=(
            "Clear, specific task description with ALL actual values included "
            "(passwords, emails, URLs) - no references like 'provided password'"
        )
    )
    expected_output: str = Field(description="What this agent should produce")
    depends_on_previous: bool = Field(
        description="True if this subtask needs output from the previous subtask"
    )


class TaskPlan(BaseModel):
    """Task plan with reasoning and ordered subtasks."""

    reasoning: str = Field(
        description="Analysis of the task and orchestration strategy"
    )
    subtasks: List[SubTask] = Field(
        description=(
            "List of subtasks in execution order. MUST have at least 1 subtask for any action "
            "request. Empty list ONLY for pure conversational queries like 'hello' or 'how are you'."
        ),
        min_length=0,
    )


class ComputerUseCrew:
    """
    CrewAI-powered computer automation system.
    Uses CrewAI's Agent, Task, and Crew for proper multi-agent orchestration.
    """

    _cancellation_requested = False

    @classmethod
    def request_cancellation(cls) -> None:
        """Request cancellation of current task execution."""
        cls._cancellation_requested = True

    @classmethod
    def clear_cancellation(cls) -> None:
        """Clear cancellation flag for new task."""
        cls._cancellation_requested = False

    @classmethod
    def is_cancelled(cls) -> bool:
        """Check if cancellation has been requested."""
        return cls._cancellation_requested

    def __init__(
        self,
        capabilities: Any,
        safety_checker: Any,
        llm_client: Optional[Any] = None,
        vision_llm_client: Optional[Any] = None,
        browser_llm_client: Optional[Any] = None,
        confirmation_manager: Optional[Any] = None,
        use_browser_profile: bool = False,
        browser_profile_directory: str = "Default",
    ) -> None:
        self.capabilities = capabilities
        self.safety_checker = safety_checker
        self.confirmation_manager = confirmation_manager
        self.use_browser_profile = use_browser_profile
        self.browser_profile_directory = browser_profile_directory

        self.llm = llm_client or LLMConfig.get_llm()
        self.vision_llm = vision_llm_client or LLMConfig.get_vision_llm()
        self.browser_llm = browser_llm_client or LLMConfig.get_browser_llm()

        self.agents_config = self._load_yaml_config("agents.yaml")
        self.tasks_config = self._load_yaml_config("tasks.yaml")

        self.tool_registry = self._initialize_tool_registry()
        self.browser_agent = self._initialize_browser_agent()
        self.coding_agent = self._initialize_coding_agent()

        self.gui_tools = self._initialize_gui_tools()
        self.web_automation_tool = self._initialize_web_tool()
        self.coding_automation_tool = self._initialize_coding_tool()
        self.execute_command_tool = self._initialize_system_tool()

        self.crew: Optional[Crew] = None
        self.platform_context = self._get_platform_context()

    # --- Initialization helpers -------------------------------------------------

    def _load_yaml_config(self, filename: str) -> Dict[str, Any]:
        config_path = Path(__file__).parent / "config" / filename
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _initialize_tool_registry(self) -> PlatformToolRegistry:
        coordinate_validator = CoordinateValidator(
            self.capabilities.screen_resolution[0],
            self.capabilities.screen_resolution[1],
        )
        return PlatformToolRegistry(
            self.capabilities,
            safety_checker=self.safety_checker,
            coordinate_validator=coordinate_validator,
            llm_client=self.browser_llm,
        )

    def _initialize_browser_agent(self) -> BrowserAgent:
        return BrowserAgent(
            llm_client=self.browser_llm,
            use_user_profile=self.use_browser_profile,
            profile_directory=self.browser_profile_directory,
        )

    def _initialize_coding_agent(self) -> CodingAgent:
        return CodingAgent()

    def _initialize_gui_tools(self) -> Dict[str, Any]:
        tools = {
            "take_screenshot": TakeScreenshotTool(),
            "click_element": ClickElementTool(),
            "type_text": TypeTextTool(),
            "open_application": OpenApplicationTool(),
            "read_screen_text": ReadScreenTextTool(),
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
        tool = WebAutomationTool()
        tool._browser_agent = self.browser_agent
        return tool

    def _initialize_coding_tool(self) -> CodingAgentTool:
        tool = CodingAgentTool()
        tool._coding_agent = self.coding_agent
        return tool

    def _initialize_system_tool(self) -> ExecuteShellCommandTool:
        tool = ExecuteShellCommandTool()
        tool._safety_checker = self.safety_checker
        tool._confirmation_manager = self.confirmation_manager
        return tool

    # --- Agent and tool construction -------------------------------------------

    def _build_tool_map(self) -> Dict[str, Any]:
        return {
            "web_automation": self.web_automation_tool,
            "coding_automation": self.coding_automation_tool,
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
        tool_map = self._build_tool_map()

        manager_agent = self._create_agent(
            "manager", [], self.llm, tool_map, is_manager=True
        )

        browser_tools = self.agents_config["browser_agent"].get("tools", [])
        gui_tools = self.agents_config["gui_agent"].get("tools", [])
        system_tools = self.agents_config["system_agent"].get("tools", [])
        coding_tools = self.agents_config["coding_agent"].get("tools", [])

        browser_agent = self._create_agent(
            "browser_agent", browser_tools, self.llm, tool_map
        )
        gui_agent = self._create_agent(
            "gui_agent", gui_tools, self.vision_llm, tool_map
        )
        system_agent = self._create_agent(
            "system_agent", system_tools, self.llm, tool_map
        )
        coding_agent = self._create_agent(
            "coding_agent", coding_tools, self.llm, tool_map
        )

        return {
            "manager": manager_agent,
            "browser_agent": browser_agent,
            "gui_agent": gui_agent,
            "system_agent": system_agent,
            "coding_agent": coding_agent,
        }

    # --- Task planning and context ---------------------------------------------

    def _get_platform_context(self) -> str:
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

        return f"\n\n🖥️  PLATFORM: {platform_name} {os_version} ({machine})\n"

    def _extract_context_from_history(
        self, conversation_history: List[Dict[str, Any]]
    ) -> str:
        if not conversation_history:
            return ""

        last_interaction = conversation_history[-1]
        if "result" not in last_interaction or not last_interaction["result"]:
            return ""

        result_data = last_interaction["result"]
        if isinstance(result_data, dict) and "result" in result_data:
            return f"\n\nPREVIOUS TASK OUTPUT:\n{result_data['result']}\n"

        return ""

    def _generate_task_plan(self, task: str) -> TaskPlan:
        orchestration_prompt = get_orchestration_prompt(task)
        orchestration_llm = LLMConfig.get_orchestration_llm()
        structured_llm = orchestration_llm.with_structured_output(TaskPlan)
        return structured_llm.invoke([HumanMessage(content=orchestration_prompt)])

    def _display_plan(self, plan: TaskPlan) -> None:
        """Display the task plan and update dashboard."""
        dashboard.add_log_entry(
            ActionType.PLAN,
            f"Analyzed: {plan.reasoning[:50]}...",
            status="complete",
        )
        dashboard.set_steps(0, len(plan.subtasks))

        if dashboard.verbosity.value >= 1:
            print_info(f"Analysis: {plan.reasoning}")
            print_info(f"Plan: {len(plan.subtasks)} subtask(s)")
            for i, subtask in enumerate(plan.subtasks, 1):
                print_info(
                    f"  {i}. {subtask.agent_type}: {subtask.description[:60]}..."
                )

    def _build_tasks_from_plan(
        self, plan: TaskPlan, context_str: str, agents_dict: Dict[str, Agent]
    ) -> tuple[list[Task], list[Agent]]:
        """Build CrewAI tasks from the plan and update dashboard progress."""
        crew_agents: list[Agent] = []
        crew_tasks: list[Task] = []

        for idx, subtask in enumerate(plan.subtasks):
            agent_key = f"{subtask.agent_type}_agent"
            if agent_key not in agents_dict:
                print_failure(f"Invalid agent: {subtask.agent_type}, skipping")
                continue

            agent = agents_dict[agent_key]
            crew_agents.append(agent)

            dashboard.set_steps(idx + 1, len(plan.subtasks))

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

        return crew_tasks, crew_agents

    # --- Crew execution --------------------------------------------------------

    def _unique_agents(self, agents: List[Agent]) -> List[Agent]:
        seen = set()
        unique_list = []
        for agent in agents:
            if agent not in seen:
                unique_list.append(agent)
                seen.add(agent)
        return unique_list

    async def _run_crew(
        self, task: str, crew_agents: List[Agent], crew_tasks: List[Task]
    ) -> TaskExecutionResult:
        """Execute the crew and update dashboard progress."""
        if not crew_tasks:
            return TaskExecutionResult(
                task=task,
                overall_success=True,
                result="Hello! I'm ready to help you with computer automation tasks. What would you like me to do?",
                error=None,
            )

        self.crew = Crew(
            agents=self._unique_agents(crew_agents),
            tasks=crew_tasks,
            process=Process.sequential,
            verbose=False,
        )

        dashboard.add_log_entry(
            ActionType.EXECUTE,
            f"Executing {len(crew_agents)} agent(s), {len(crew_tasks)} task(s)",
            status="pending",
        )

        if crew_agents:
            first_agent_role = crew_agents[0].role if crew_agents[0].role else "Agent"
            dashboard.set_agent(first_agent_role)

        print_success(
            f"Executing {len(crew_agents)} agent(s), {len(crew_tasks)} task(s)"
        )

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self.crew.kickoff)
            dashboard.set_steps(len(crew_tasks), len(crew_tasks))
            print_success("Execution completed")
            return TaskExecutionResult(
                task=task, result=str(result), overall_success=True
            )
        except asyncio.CancelledError:
            print_failure("Task cancelled by user")
            return TaskExecutionResult(
                task=task,
                result=None,
                overall_success=False,
                error="Task cancelled by user (ESC pressed)",
            )
        except ValueError as exc:
            if "Invalid response from LLM call" not in str(exc):
                raise
            print_warning("LLM returned empty response, retrying...")
            try:
                result = await loop.run_in_executor(None, self.crew.kickoff)
                print_success("Execution completed after retry")
                return TaskExecutionResult(
                    task=task, result=str(result), overall_success=True
                )
            except Exception as retry_err:
                print_failure(f"Retry failed: {retry_err}")
                return TaskExecutionResult(
                    task=task,
                    overall_success=False,
                    error=str(retry_err),
                )

    # --- Public API ------------------------------------------------------------

    async def execute_task(
        self,
        task: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskExecutionResult:
        """Execute a task using the crew system with dashboard updates."""
        conversation_history = conversation_history or []

        try:
            dashboard.set_action("Planning", "Analyzing task...")

            context_str = self._extract_context_from_history(conversation_history)
            plan = self._generate_task_plan(task)
            self._display_plan(plan)

            dashboard.set_action("Building", "Creating agents...")
            agents_dict = self._create_crewai_agents()
            crew_tasks, crew_agents = self._build_tasks_from_plan(
                plan, context_str, agents_dict
            )

            if not crew_tasks:
                dashboard.clear_action()
                print_info("Conversational message detected")
                return TaskExecutionResult(
                    task=task,
                    overall_success=True,
                    result=plan.reasoning
                    or "Hello! I'm ready to help. What would you like me to do?",
                    error=None,
                )

            result = await self._run_crew(task, crew_agents, crew_tasks)

            if result and hasattr(result, "result"):
                conversation_history.append({"user": task, "result": result})
                if len(conversation_history) > 10:
                    conversation_history[:] = conversation_history[-10:]

            dashboard.clear_action()
            return result

        except asyncio.CancelledError:
            dashboard.clear_action()
            print_failure("Task cancelled by user")
            return TaskExecutionResult(
                task=task,
                result=None,
                overall_success=False,
                error="Task cancelled by user (ESC pressed)",
            )
        except Exception as exc:
            dashboard.clear_action()
            print_failure(f"Execution failed: {exc}")
            return TaskExecutionResult(
                task=task,
                overall_success=False,
                error=str(exc),
            )
