"""CrewAI-based multi-agent computer automation system with hierarchical delegation."""

import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from crewai import Agent, Crew, Process, Task

from .agents.browser_agent import BrowserAgent
from .agents.coding_agent import CodingAgent
from .config.llm_config import LLMConfig
from .schemas import TaskExecutionResult
from .services.state import get_app_state
from .services.crew import (
    CrewAgentFactory,
    CrewGuiDelegate,
    CrewToolsFactory,
    LLMEventService,
)
from .tools.platform_registry import PlatformToolRegistry
from .utils.logging import debug_log, update_crew_token_usage
from .utils.platform import PlatformHelper
from .utils.validation import CoordinateValidator
from .utils.ui import (
    ActionType,
    dashboard,
    print_failure,
    print_success,
)

AGENT_DISPLAY_NAMES = {
    "Task Orchestration Manager": "Manager",
    "Web Automation Specialist": "Browser Agent",
    "Desktop Application Automation Expert": "GUI Agent",
    "System Command & Terminal Expert": "System Agent",
    "Code Automation Specialist": "Coding Agent",
}


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
        self.platform_context = PlatformHelper.get_platform_context_string()

        self.tool_registry = self._initialize_tool_registry()
        self._initialize_app_state()
        self.gui_tools = self._initialize_gui_tools()
        self.observation_tools = self._initialize_observation_tools()

        self.browser_agent = self._initialize_browser_agent()
        self.coding_agent = self._initialize_coding_agent()

        self.web_automation_tool = self._initialize_web_tool()
        self.coding_automation_tool = self._initialize_coding_tool()
        self.execute_command_tool = self._initialize_system_tool()

        self.crew: Optional[Crew] = None
        self._cached_agents: Optional[Dict[str, Agent]] = None
        self._last_token_update: float = 0

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

    def _initialize_app_state(self) -> None:
        """Initialize the centralized app state manager with accessibility tool."""
        accessibility_tool = self.tool_registry.get_tool("accessibility")
        if accessibility_tool:
            get_app_state().set_accessibility_tool(accessibility_tool)

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
        return CrewToolsFactory.create_gui_tools(self.tool_registry)

    def _initialize_observation_tools(self) -> Dict[str, Any]:
        return CrewToolsFactory.create_observation_tools(self.tool_registry)

    def _initialize_web_tool(self) -> Any:
        return CrewToolsFactory.create_web_tool(self.browser_agent)

    def _initialize_coding_tool(self) -> Any:
        return CrewToolsFactory.create_coding_tool(self.coding_agent)

    def _initialize_system_tool(self) -> Any:
        return CrewToolsFactory.create_system_tool(
            self.safety_checker, self.confirmation_manager
        )

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
        tool_map = {
            "web_automation": self.web_automation_tool,
            "coding_automation": self.coding_automation_tool,
            **self.gui_tools,
            **self.observation_tools,
            "execute_shell_command": self.execute_command_tool,
        }
        return tool_map

    def _create_step_callback(self, agent_role: str):
        """
        Create a callback for agent step logging.

        Args:
            agent_role: The role/name of the agent for dashboard display
        """
        display_name = AGENT_DISPLAY_NAMES.get(agent_role.strip(), agent_role)
        is_manager = display_name == "Manager"

        def step_callback(step_output):
            if self.is_cancelled():
                raise KeyboardInterrupt("Task cancelled by user")

            current_agent = dashboard.get_current_agent_name()
            if is_manager and current_agent and current_agent != "Manager":
                return

            dashboard.set_agent(display_name)

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
                    elif not text.startswith(":") and len(text) > 20:
                        thought = text

                if thought:
                    thought = thought.replace("Thought:", "").strip()
                    if self._is_valid_reasoning(thought):
                        dashboard.set_thinking(thought)
                        dashboard._show_status("Processing...")

                if is_manager and hasattr(step, "tool"):
                    if step.tool == "Delegate work to coworker":
                        tool_input = getattr(step, "tool_input", {})
                        if isinstance(tool_input, dict):
                            agent_name = tool_input.get("coworker", "agent")
                            display_agent = AGENT_DISPLAY_NAMES.get(
                                agent_name.strip(), agent_name
                            )
                            task_desc = str(tool_input.get("task", "task"))[:100]
                            dashboard.log_delegation(display_agent, task_desc)

                if (
                    not is_manager
                    and hasattr(step, "tool")
                    and hasattr(step, "tool_input")
                ):
                    tool_name = step.tool
                    if tool_name and tool_name != "Delegate work to coworker":
                        dashboard._show_status(f"Running {tool_name}...")

            self._update_token_usage()

        return step_callback

    def _is_valid_reasoning(self, text: str) -> bool:
        """
        Check if text is valid reasoning vs tool output/junk/verbose prompts.

        Args:
            text: Text to validate

        Returns:
            True if valid reasoning worth displaying
        """
        if not text or len(text) < 10:
            return False

        text_lower = text.lower()

        if "delegate" in text_lower or "delegating" in text_lower:
            return True

        invalid_starts = [
            ": true",
            ": false",
            ": none",
            "true",
            "false",
            "none",
            "success=",
            "error=",
            '{"',
            "{'",
            "action:",
        ]
        for pattern in invalid_starts:
            if text_lower.startswith(pattern):
                return False

        invalid_contains = [
            "use the following format",
            "begin!",
        ]
        for pattern in invalid_contains:
            if pattern.lower() in text_lower:
                return False

        if len(text) > 300:
            return False

        return True

    def _update_token_usage(self) -> None:
        """Update dashboard with current token usage using CrewAI's built-in metrics."""
        self._last_token_update = update_crew_token_usage(
            self.crew, self._last_token_update
        )

    def _create_agent(
        self,
        config_key: str,
        tool_names: List[str],
        llm: Any,
        tool_map: Dict[str, Any],
    ) -> Agent:
        """Create a CrewAI agent from configuration."""
        config = self.agents_config[config_key]
        return CrewAgentFactory.create_agent(
            config_key=config_key,
            config=config,
            tool_names=tool_names,
            llm=llm,
            tool_map=tool_map,
            platform_context=self.platform_context,
            step_callback_factory=self._create_step_callback,
            agent_display_names=AGENT_DISPLAY_NAMES,
        )

    def _create_crewai_agents(self) -> Dict[str, Agent]:
        """Create all CrewAI agents for the hierarchical crew."""
        tool_map = self._build_tool_map()

        browser_tools = self.agents_config["browser_agent"].get("tools", [])
        gui_tools = self.agents_config["gui_agent"].get("tools", [])
        system_tools = self.agents_config["system_agent"].get("tools", [])
        coding_tools = self.agents_config["coding_agent"].get("tools", [])

        manager_agent = self._create_agent("manager", [], self.llm, tool_map)

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

    def _get_or_create_agents(self) -> Dict[str, Agent]:
        """
        Get cached agents or create new ones if not cached.
        Reuses agents across task executions for better performance.
        """
        if self._cached_agents is None:
            self._cached_agents = self._create_crewai_agents()
        return self._cached_agents

    def clear_agent_cache(self) -> None:
        """Clear cached agents to force recreation on next task."""
        self._cached_agents = None

    def _create_manager_task(self, task: str, context_str: str) -> Task:
        """Create the manager task for hierarchical delegation."""
        task_description = task
        if context_str:
            task_description = f"{task}{context_str}"

        return Task(
            description=f"""USER REQUEST: {task_description}

Understand what the user wants to achieve, then delegate to the appropriate specialist.

CRITICAL:
- Use any provided SYSTEM STATE context verbatim when delegating.
- Pass EXACT file paths/URLs between agents (never paraphrase)
- Browser tasks = ONE delegation (session continuity)

VERIFICATION REQUIREMENT:
- You MUST verify outcomes with CONCRETE evidence from tool outputs
- If specialist returns error, "couldn't generate", or "No elements found" = TASK FAILED
- NEVER claim success without specific tool output proving the action was completed
- If task failed, report FAILURE honestly - do not fabricate success""",
            expected_output="""Either:
A) SUCCESS - with concrete evidence:
   - Specific tool outputs showing action was completed
   - Verification showing the result (e.g., message sent, file created)

OR

B) FAILURE - with honest explanation:
   - What was attempted
   - What specific error or issue occurred
   - Why the task could not be completed""",
        )

    def _setup_llm_event_handlers(self) -> None:
        """Subscribe to CrewAI LLM events for real-time status updates."""
        LLMEventService.setup_handlers()

    async def _run_hierarchical_crew(
        self, task: str, context_str: str
    ) -> TaskExecutionResult:
        """Execute the hierarchical crew with thread-based execution."""
        debug_log(
            "H_CREW_KICKOFF",
            "crew.py:_run_hierarchical_crew:enter",
            "Starting hierarchical crew",
            {
                "task_len": len(task or ""),
                "task_sha8": hashlib.sha256((task or "").encode("utf-8")).hexdigest()[
                    :8
                ],
                "llm_provider": os.getenv("LLM_PROVIDER"),
                "llm_model": os.getenv("LLM_MODEL"),
                "vision_llm_provider": os.getenv("VISION_LLM_PROVIDER"),
                "vision_llm_model": os.getenv("VISION_LLM_MODEL"),
                "llm_timeout": os.getenv("LLM_TIMEOUT"),
            },
        )
        dashboard.add_log_entry(
            ActionType.EXECUTE,
            "Starting hierarchical execution",
            status="pending",
        )
        dashboard.set_agent("Manager")
        dashboard.set_thinking("Analyzing task and delegating...")

        self._setup_llm_event_handlers()

        agents_dict = self._get_or_create_agents()
        system_state_context = ""
        try:
            state_tool = self.observation_tools.get("get_system_state")
            if state_tool:
                state_result = state_tool._run(scope="standard")
                if (
                    getattr(state_result, "success", False)
                    and isinstance(getattr(state_result, "data", None), dict)
                    and state_result.data.get("context_for_delegation")
                ):
                    system_state_context = (
                        "\n\nSYSTEM STATE (for delegation):\n"
                        f"{state_result.data['context_for_delegation']}\n"
                    )
        except Exception:
            system_state_context = ""

        manager_task = self._create_manager_task(
            task, context_str + system_state_context
        )

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
            verbose=dashboard.is_verbose,
        )

        loop = asyncio.get_event_loop()
        try:
            t0 = time.time()
            debug_log(
                "H_CREW_KICKOFF",
                "crew.py:_run_hierarchical_crew:before_kickoff",
                "Calling CrewAI kickoff in executor",
                {"executor_loop_running": bool(loop.is_running())},
            )
            result = await loop.run_in_executor(None, self.crew.kickoff)
            debug_log(
                "H_CREW_KICKOFF",
                "crew.py:_run_hierarchical_crew:after_kickoff",
                "CrewAI kickoff returned",
                {
                    "elapsed_ms": int((time.time() - t0) * 1000),
                    "result_type": type(result).__name__,
                },
            )

            if hasattr(result, "token_usage") and result.token_usage:
                tu = result.token_usage
                if isinstance(tu, dict):
                    prompt = tu.get("prompt_tokens", 0)
                    completion = tu.get("completion_tokens", 0)
                else:
                    prompt = getattr(tu, "prompt_tokens", 0)
                    completion = getattr(tu, "completion_tokens", 0)
                dashboard.update_token_usage(prompt, completion)

            result_str = str(result)
            print_success("Execution completed")
            return TaskExecutionResult(
                task=task, result=result_str, overall_success=True
            )
        except Exception as exc:
            import traceback

            tb_str = traceback.format_exc()
            print(f"\n[CREW ERROR] {type(exc).__name__}: {exc}")
            print(f"[TRACEBACK]\n{tb_str[:500]}")
            debug_log(
                "H_CREW_KICKOFF",
                "crew.py:_run_hierarchical_crew:exception",
                "CrewAI kickoff raised",
                {
                    "exc_type": type(exc).__name__,
                    "exc_str": str(exc)[:500],
                    "traceback": tb_str[:1000],
                },
            )
            if self._cancellation_requested:
                print_failure("Task cancelled by user")
                return TaskExecutionResult(
                    task=task,
                    result=None,
                    overall_success=False,
                    error="Task cancelled by user",
                )
            print_failure(f"Execution failed: {exc}")
            return TaskExecutionResult(task=task, overall_success=False, error=str(exc))

    async def execute_task(
        self,
        task: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskExecutionResult:
        """Execute a task using hierarchical crew delegation."""
        conversation_history = conversation_history or []
        self.clear_agent_cache()

        try:
            from .utils.threading.main_thread import set_main_event_loop

            try:
                set_main_event_loop(asyncio.get_running_loop())
            except RuntimeError:
                pass

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
        finally:
            get_app_state().clear_target_app()
