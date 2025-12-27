"""CrewAI-based multi-agent computer automation system with hierarchical delegation."""

import asyncio
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from crewai import Agent, Crew, Process, Task

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
from .schemas import TaskExecutionResult
from .tools.platform_registry import PlatformToolRegistry
from .utils.coordinate_validator import CoordinateValidator
from .utils.ui import (
    ActionType,
    dashboard,
    print_failure,
    print_success,
)
from .services.crew_gui_delegate import CrewGuiDelegate


class ComputerUseCrew:
    """
    CrewAI-powered computer automation system.
    Uses hierarchical process for dynamic agent delegation at runtime.
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
        self.platform_context = self._get_platform_context()

        self.tool_registry = self._initialize_tool_registry()
        self.gui_tools = self._initialize_gui_tools()

        self.browser_agent = self._initialize_browser_agent()
        self.coding_agent = self._initialize_coding_agent()

        self.web_automation_tool = self._initialize_web_tool()
        self.coding_automation_tool = self._initialize_coding_tool()
        self.execute_command_tool = self._initialize_system_tool()

        self.crew: Optional[Crew] = None

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
        gui_delegate = CrewGuiDelegate(
            agents_config=self.agents_config,
            tool_map=self.gui_tools,
            platform_context=self.platform_context,
            gui_llm=self.vision_llm,
        )
        return BrowserAgent(
            llm_client=self.browser_llm,
            use_user_profile=self.use_browser_profile,
            profile_directory=self.browser_profile_directory,
            gui_delegate=gui_delegate,
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

    def _get_platform_context(self) -> str:
        os_name = platform.system()
        platform_names = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}
        platform_name = platform_names.get(os_name, os_name)
        return f"\n\n🖥️  PLATFORM: {platform_name} {platform.release()} ({platform.machine()})\n"

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

    def _build_tool_map(self) -> Dict[str, Any]:
        return {
            "web_automation": self.web_automation_tool,
            "coding_automation": self.coding_automation_tool,
            **self.gui_tools,
            "execute_shell_command": self.execute_command_tool,
        }

    def _create_step_callback(self, agent_role: str):
        """
        Create a callback for agent step logging.

        Args:
            agent_role: The role/name of the agent for dashboard display
        """

        def step_callback(step_output):
            if self.is_cancelled():
                raise KeyboardInterrupt("Task cancelled by user")

            dashboard.set_agent(agent_role)

            steps = step_output if isinstance(step_output, list) else [step_output]
            for step in steps:
                thought = None
                if hasattr(step, "thought") and step.thought:
                    thought = step.thought.strip()
                elif hasattr(step, "text") and step.text:
                    text = step.text.strip()
                    if "\nAction:" in text:
                        thought = text.split("\nAction:")[0].strip()
                    elif "\nFinal Answer:" in text:
                        thought = text.split("\nFinal Answer:")[0].strip()
                    else:
                        thought = text

                if thought:
                    thought = thought.replace("Thought:", "").strip()
                    dashboard.set_thinking(thought)

                if hasattr(step, "tool") and hasattr(step, "tool_input"):
                    dashboard.log_tool_start(step.tool, step.tool_input)

            self._update_token_usage()
            dashboard.set_action("Thinking", "planning next action...")

        return step_callback

    def _update_token_usage(self) -> None:
        """Update dashboard with current token usage from all agents."""
        if not hasattr(self, "crew") or not self.crew:
            return

        try:
            total_input = 0
            total_output = 0

            all_agents = list(self.crew.agents) if self.crew.agents else []
            if hasattr(self.crew, "manager_agent") and self.crew.manager_agent:
                all_agents.append(self.crew.manager_agent)

            for agent in all_agents:
                if hasattr(agent, "llm") and hasattr(agent.llm, "_token_usage"):
                    usage = agent.llm._token_usage
                    total_input += usage.get("prompt_tokens", 0)
                    total_output += usage.get("completion_tokens", 0)

            dashboard.update_token_usage(total_input, total_output)
        except Exception:
            pass

    def _create_agent(
        self,
        config_key: str,
        tool_names: List[str],
        llm: Any,
        tool_map: Dict[str, Any],
        is_manager: bool = False,
    ) -> Agent:
        """Create a CrewAI agent from configuration."""
        config = self.agents_config[config_key]
        tools = [tool_map[name] for name in tool_names if name in tool_map]
        backstory_with_context = config["backstory"] + self.platform_context
        agent_role = config["role"]

        agent_params = {
            "role": agent_role,
            "goal": config["goal"],
            "backstory": backstory_with_context,
            "verbose": False,
            "llm": llm,
            "max_iter": config.get("max_iter", 15),
            "allow_delegation": config.get("allow_delegation", False),
            "memory": True,
            "step_callback": self._create_step_callback(agent_role),
        }

        if is_manager:
            agent_params["tools"] = []
        else:
            agent_params["tools"] = tools

        return Agent(**agent_params)

    def _create_crewai_agents(self) -> Dict[str, Agent]:
        """Create all CrewAI agents for the hierarchical crew."""
        tool_map = self._build_tool_map()

        manager_agent = self._create_agent(
            "manager", [], self.llm, tool_map, is_manager=True
        )

        browser_tools = self.agents_config["browser_agent"].get("tools", [])
        gui_tools = self.agents_config["gui_agent"].get("tools", [])
        system_tools = self.agents_config["system_agent"].get("tools", [])
        coding_tools = self.agents_config["coding_agent"].get("tools", [])

        return {
            "manager": manager_agent,
            "browser_agent": self._create_agent(
                "browser_agent", browser_tools, self.llm, tool_map
            ),
            "gui_agent": self._create_agent(
                "gui_agent", gui_tools, self.vision_llm, tool_map
            ),
            "system_agent": self._create_agent(
                "system_agent", system_tools, self.llm, tool_map
            ),
            "coding_agent": self._create_agent(
                "coding_agent", coding_tools, self.llm, tool_map
            ),
        }

    def _create_manager_task(self, task: str, context_str: str) -> Task:
        """Create the manager task for hierarchical delegation."""
        task_description = task
        if context_str:
            task_description = f"{task}{context_str}"

        return Task(
            description=f"""Complete this user request by delegating to the appropriate specialist agents:

USER REQUEST: {task_description}

Analyze the request and delegate to the right specialist(s):
- Web Automation Specialist: Web browsing, data extraction, website interactions, AI image generation (has built-in generate_image tool), phone/SMS verification
- Desktop Application Automation Expert: GUI apps, clicking, typing, file operations via UI, native OS dialogs, system settings and preferences (wallpaper, theme, sound, etc.)
- System Command & Terminal Expert: Shell commands, CLI operations, file system via terminal (ls, cp, mv, etc.)
- Code Automation Specialist: Writing code, debugging, refactoring, testing

IMPORTANT:
- You can delegate to multiple agents sequentially if the task requires it
- Pass results from one agent to the next when there are dependencies
- CRITICAL: Pass EXACT file paths and data between agents. If Agent A returns a path like '/private/tmp/downloads/file.jpg', pass that EXACT path to Agent B. DO NOT simplify or assume standard paths.
- For browser tasks, delegate the ENTIRE browser portion as ONE task (to maintain session)
- Report the final consolidated result after all delegations complete""",
            expected_output="""A clear, complete response addressing the user's request. Include:
1. Summary of what was accomplished
2. Any data, files, or results produced
3. Confirmation of successful completion or explanation of any issues encountered""",
        )

    async def _run_hierarchical_crew(
        self, task: str, context_str: str
    ) -> TaskExecutionResult:
        """Execute the hierarchical crew with thread-based execution."""
        dashboard.add_log_entry(
            ActionType.EXECUTE,
            "Starting hierarchical execution",
            status="pending",
        )
        dashboard.set_agent("Task Orchestration Manager")

        agents_dict = self._create_crewai_agents()
        manager_task = self._create_manager_task(task, context_str)

        specialist_agents = [
            agents_dict["browser_agent"],
            agents_dict["gui_agent"],
            agents_dict["system_agent"],
            agents_dict["coding_agent"],
        ]

        self.crew = Crew(
            agents=specialist_agents,
            tasks=[manager_task],
            process=Process.hierarchical,
            manager_agent=agents_dict["manager"],
            verbose=False,
        )

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self.crew.kickoff)
            print_success("Execution completed")
            return TaskExecutionResult(
                task=task, result=str(result), overall_success=True
            )
        except Exception as exc:
            if self._cancellation_requested:
                print_failure("Task cancelled by user")
                return TaskExecutionResult(
                    task=task,
                    result=None,
                    overall_success=False,
                    error="Task cancelled by user",
                )
            print_failure(f"Execution failed: {exc}")
            return TaskExecutionResult(
                task=task, overall_success=False, error=str(exc)
            )

    async def execute_task(
        self,
        task: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskExecutionResult:
        """Execute a task using hierarchical crew delegation."""
        conversation_history = conversation_history or []

        try:
            dashboard.set_action("Analyzing", "Processing request...")

            context_str = self._extract_context_from_history(conversation_history)

            result = await self._run_hierarchical_crew(task, context_str)

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
