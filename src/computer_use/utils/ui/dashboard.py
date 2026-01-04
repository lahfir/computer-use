"""
Main dashboard manager - orchestrates all UI components.
Real-time, immediate output with proper visual hierarchy.

Uses Rich renderers for consistent formatting and animations for feedback.
"""

import sys
import time
import threading
import uuid
from typing import Any, Dict, List, Optional, Set

from rich.console import Console
from rich.status import Status
from rich.text import Text

from .state import TaskState, AgentState, ToolState, VerbosityLevel, ActionType
from .theme import THEME, ICONS
from .renderers import (
    AgentRenderer,
    ToolRenderer,
    ThinkingRenderer,
    StatusBarRenderer,
)


class LogBatcher:
    """Batch log entries to reduce UI updates."""

    def __init__(self, batch_size: int = 10, timeout_sec: float = 0.2):
        self._batch: List[tuple] = []
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._batch_size = batch_size
        self._timeout_sec = timeout_sec

    def add(
        self,
        action_type: ActionType,
        message: str,
        target: Optional[str] = None,
        status: str = "pending",
    ) -> None:
        with self._lock:
            self._batch.append((action_type, message, target, status))
            if len(self._batch) >= self._batch_size:
                self._flush_locked()
            elif self._timer is None:
                self._timer = threading.Timer(self._timeout_sec, self._flush)
                self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._batch:
            return

        count = len(self._batch)
        last = self._batch[-1]
        action_type, message, target, status = last

        if count > 1:
            message = f"{message} (+{count - 1} more)"

        dashboard.add_log_entry(action_type, message, target, status)
        self._batch.clear()

        if self._timer:
            self._timer.cancel()
            self._timer = None

    def flush_now(self) -> None:
        self._flush()


class DashboardManager:
    """
    High-performance singleton dashboard manager.
    Real-time output with immediate flushing.
    """

    _instance: Optional["DashboardManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DashboardManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self.console = Console(force_terminal=True, force_interactive=False)
        self.verbosity = VerbosityLevel.NORMAL

        # Current task state
        self._task: Optional[TaskState] = None
        self._is_running = False

        # Renderers - use these for consistent formatting
        self._agent_renderer = AgentRenderer(self.console, self.verbosity)
        self._tool_renderer = ToolRenderer(self.console, self.verbosity)
        self._thinking_renderer = ThinkingRenderer(self.console, self.verbosity)
        self._status_renderer = StatusBarRenderer(self.console, self.verbosity)

        # Track what's been printed (avoid duplicates)
        self._printed_agents: Set[str] = set()
        self._printed_tools: Set[str] = set()
        self._last_thought_hash: Optional[int] = None
        self._header_printed = False
        self._current_agent_name: Optional[str] = None

        # Tool history for explorer
        self._tool_history: List[Dict[str, Any]] = []

        # Rich Status for animated spinner between actions
        self._status: Optional[Status] = None
        self._current_status_text: str = ""
        self._status_timer: Optional[threading.Timer] = None

    def _flush(self) -> None:
        """Force flush output to terminal immediately."""
        sys.stdout.flush()
        sys.stderr.flush()

    def _print(self, text: Text) -> None:
        """Print with immediate flush, pausing status spinner."""
        if self._status:
            self._status.stop()
            self._status = None
        self.console.print(text)
        self._flush()

    def _print_raw(self, content: str) -> None:
        """Print raw string with immediate flush, pausing status spinner."""
        if self._status:
            self._status.stop()
            self._status = None
        self.console.print(content)
        self._flush()

    @property
    def is_quiet(self) -> bool:
        return self.verbosity == VerbosityLevel.QUIET

    @property
    def is_verbose(self) -> bool:
        return self.verbosity == VerbosityLevel.VERBOSE

    def set_verbosity(self, level: VerbosityLevel) -> None:
        self.verbosity = level

    # ─────────────────────────────────────────────────────────────────────
    # Task lifecycle
    # ─────────────────────────────────────────────────────────────────────

    def set_task(self, description: str) -> None:
        """Initialize a new task."""
        self._task = TaskState(
            task_id=str(uuid.uuid4()),
            description=description,
            status="running",
        )
        self._printed_agents.clear()
        self._printed_tools.clear()
        self._last_thought_hash = None
        self._header_printed = False
        self._current_agent_name = None
        self._tool_history.clear()

    def start_dashboard(self) -> None:
        """Start the dashboard display."""
        if self.is_quiet or self._is_running:
            return

        self._is_running = True
        self._print_task_header()
        self._start_live_status()

    def stop_dashboard(self, print_log: bool = True, cancelled: bool = False) -> None:
        """Stop the dashboard and optionally print summary."""
        if not self._is_running:
            return

        self._is_running = False
        self._stop_live_status()

        if self._task and self._task.active_agent_id and not cancelled:
            final_agent = self._task.agents.get(self._task.active_agent_id)
            if final_agent and final_agent.tools:
                self._print_agent_summary(final_agent)

        if print_log and self._task and not cancelled:
            self.console.print()
            self.print_session_log()

    def complete_task(self, success: bool = True) -> None:
        """Mark the current task as complete."""
        if self._task:
            self._task.status = "complete" if success else "error"
            self._task.end_time = time.time()

    # ─────────────────────────────────────────────────────────────────────
    # Agent API
    # ─────────────────────────────────────────────────────────────────────

    def set_agent(self, agent_name: str) -> None:
        """Set the active agent. Only prints header once per agent."""
        if not self._task:
            return

        agent_name = agent_name.strip()

        if agent_name == self._current_agent_name:
            return

        if self._current_agent_name and self._task.active_agent_id:
            prev_agent = self._task.agents.get(self._task.active_agent_id)
            if prev_agent:
                self._print_agent_summary(prev_agent)

        self._current_agent_name = agent_name
        agent = self._task.set_active_agent(agent_name)

        if agent.agent_id not in self._printed_agents:
            self._printed_agents.add(agent.agent_id)
            self._print_agent_header(agent)
            self._show_status(f"{agent_name} analyzing...")

    def set_thinking(self, thought: str) -> None:
        """Set current agent's thinking/reasoning. Shows FULL text."""
        if not self._task or not self._task.active_agent_id:
            return

        if not thought or not thought.strip():
            return

        thought = thought.strip()

        # Deduplicate by hash of first 100 chars
        thought_hash = hash(thought[:100])
        if thought_hash == self._last_thought_hash:
            return
        self._last_thought_hash = thought_hash

        agent = self._task.agents.get(self._task.active_agent_id)
        if agent:
            agent.current_thought = thought
            agent.status = "thinking"
            self._print_thought_full(thought)
            short_thought = thought[:60] + "..." if len(thought) > 60 else thought
            self._show_status(short_thought)

    def set_action(self, action: str, target: Optional[str] = None) -> None:
        """Set current action description."""
        if not self._task or not self._task.active_agent_id:
            return

        agent = self._task.agents.get(self._task.active_agent_id)
        if agent:
            agent.status = "executing"

    def clear_action(self) -> None:
        """Clear the current action."""
        pass

    # ─────────────────────────────────────────────────────────────────────
    # Tool API
    # ─────────────────────────────────────────────────────────────────────

    def log_tool_start(self, tool_name: str, tool_input: Any) -> str:
        """Log tool execution start - prints immediately."""
        if not self._task or not self._task.active_agent_id:
            return ""

        agent = self._task.agents.get(self._task.active_agent_id)
        if not agent:
            return ""

        tool = agent.add_tool(tool_name, tool_input)
        self._task.total_tools += 1

        # Store in history for explorer
        self._tool_history.append(
            {
                "id": tool.tool_id,
                "name": tool_name,
                "input": tool_input,
                "output": None,
                "error": None,
                "status": "pending",
                "timestamp": time.time(),
            }
        )

        # Print immediately
        self._print_tool_start(tool)
        return tool.tool_id

    def get_pending_tool_id(self, tool_name: str = None) -> Optional[str]:
        """Find the most recent pending tool."""
        if not self._task or not self._task.active_agent_id:
            return None

        agent = self._task.agents.get(self._task.active_agent_id)
        if not agent:
            return None

        for tool in reversed(agent.tools):
            if tool.status == "pending":
                if tool_name is None or tool.name == tool_name:
                    return tool.tool_id

        return None

    def log_tool_complete(
        self,
        tool_id: str,
        success: bool,
        action_taken: str = "",
        method_used: str = "",
        confidence: float = 0.0,
        error: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log tool completion - prints immediately."""
        if not self._task:
            return

        for agent in self._task.agents.values():
            tool = agent.get_tool(tool_id)
            if tool:
                output = (
                    action_taken
                    or data
                    or (f"method={method_used}" if method_used else "success")
                )
                tool.complete(success, output, error)

                if not success:
                    self._task.failed_tools += 1

                # Update history
                for hist in self._tool_history:
                    if hist["id"] == tool_id:
                        hist["output"] = output
                        hist["error"] = error
                        hist["status"] = "success" if success else "error"
                        break

                # Print immediately
                self._print_tool_complete(tool)
                return

    # ─────────────────────────────────────────────────────────────────────
    # Token usage
    # ─────────────────────────────────────────────────────────────────────

    def update_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Update token usage counters."""
        if self._task:
            self._task.token_input = input_tokens
            self._task.token_output = output_tokens

    # ─────────────────────────────────────────────────────────────────────
    # Printing methods - REAL TIME
    # ─────────────────────────────────────────────────────────────────────

    def _print_task_header(self) -> None:
        """Print the task header."""
        if self._header_printed or not self._task:
            return
        self._header_printed = True

        self.console.print()
        self._print_raw(f"[{THEME['border']}]{'═' * 70}[/]")

        task_line = Text()
        task_line.append("  TASK: ", style=f"bold {THEME['muted']}")
        task_line.append(self._task.description, style=f"bold {THEME['text']}")
        self._print(task_line)

        self._print_raw(f"[{THEME['border']}]{'═' * 70}[/]")
        self.console.print()
        self._flush()

    def _print_agent_summary(self, agent: AgentState) -> None:
        """
        Print agent completion summary with duration and tool count.

        Format:
        └─ Agent Name ─────────────── COMPLETE ─┘
        │ Duration: 8s │ Tools: 3/3              │
        """
        duration = agent.duration
        if duration < 60:
            duration_str = f"{int(duration)}s"
        else:
            mins = int(duration // 60)
            secs = int(duration % 60)
            duration_str = f"{mins}m {secs}s"

        total_tools = len(agent.tools)
        success_tools = sum(1 for t in agent.tools if t.status == "success")

        name_part = f"└─ {agent.name} "
        stats = f" Duration: {duration_str} │ Tools: {success_tools}/{total_tools} "
        padding_len = max(1, 56 - len(agent.name) - len(stats))
        padding = "─" * padding_len
        end_part = " COMPLETE ─┘"

        summary = Text()
        summary.append(name_part, style=f"bold {THEME['tool_success']}")
        summary.append(padding, style=THEME["border"])
        summary.append(stats, style=THEME["muted"])
        summary.append(end_part, style=f"bold {THEME['tool_success']}")

        self._print(summary)
        self.console.print()

    def _print_agent_header(self, agent: AgentState) -> None:
        """Print agent header when it becomes active."""
        self.console.print()

        name_part = f"┌─ {agent.name} "
        padding = "─" * max(1, 56 - len(agent.name))
        status_part = f" {ICONS['agent_active']} ACTIVE ─┐"

        header = Text()
        header.append(name_part, style=f"bold {THEME['agent_active']}")
        header.append(padding, style=THEME["border"])
        header.append(status_part, style=f"bold {THEME['agent_active']}")

        self._print(header)

    def _print_thought_full(self, thought: str) -> None:
        """Print FULL thinking/reasoning using ThinkingRenderer."""
        thought = thought.strip()
        if not thought:
            return

        thought_line = self._thinking_renderer.render_inline(thought)
        self._print(thought_line)

    def _print_tool_start(self, tool: ToolState) -> None:
        """Print tool start using the ToolRenderer, then show waiting status."""
        if tool.tool_id in self._printed_tools:
            return

        self._printed_tools.add(tool.tool_id)

        action_desc = self._get_action_description(tool.name, tool.input_data)
        if action_desc:
            action_line = Text()
            action_line.append(
                f"  {ICONS['bullet']} ", style=f"bold {THEME['tool_pending']}"
            )
            action_line.append(action_desc, style=f"italic {THEME['text']}")
            self._print(action_line)

        tool_header = self._tool_renderer._render_tool_header(tool)
        self._print(tool_header)

        if tool.input_data:
            input_line = self._tool_renderer._render_input(tool.input_data)
            self._print(input_line)

        self._show_status(f"Running {tool.name}...")

    def _get_action_description(self, tool_name: str, input_data: Dict) -> str:
        """Generate human-readable action description."""
        if not input_data:
            return ""

        action_map = {
            "open_application": lambda d: f"Opening {d.get('app_name', 'application')}",
            "check_app_running": lambda d: f"Checking if {d.get('app_name', 'app')} is running",
            "click_element": lambda d: f"Clicking {d.get('element_id', 'element')}",
            "type_text": lambda d: "Typing text",
            "read_screen_text": lambda d: f"Reading text from {d.get('app_name', 'screen')}",
            "get_accessible_elements": lambda d: f"Scanning {d.get('app_name', 'app')} UI",
            "take_screenshot": lambda d: "Taking screenshot",
            "scroll": lambda d: f"Scrolling {d.get('direction', 'down')}",
            "web_automation": lambda d: "Running web automation",
            "execute_shell_command": lambda d: "Executing command",
            "human_assistance": lambda d: f"⚠️ Requesting human help: {d.get('reason', 'assistance needed')}",
            "request_human_assistance": lambda d: f"⚠️ Requesting human help: {d.get('reason', 'assistance needed')}",
            "delegate_task": lambda d: f"Delegating to {d.get('agent', 'agent')}",
            "coding_task": lambda d: "Running coding task",
        }

        if tool_name in action_map:
            try:
                data = input_data.get("value", input_data)
                if isinstance(data, str):
                    import json

                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {"value": data}
                return action_map[tool_name](data)
            except Exception:
                pass

        return ""

    def _print_tool_complete(self, tool: ToolState) -> None:
        """
        Print tool completion with duration in header.

        Format:
          ✓ tool_name (5.00s)
              ← output
        """
        self.console.print()
        header = self._tool_renderer._render_tool_header(tool)
        self._print(header)

        if tool.status == "success":
            output_line = self._tool_renderer._render_output(tool.output_data)
            self._print(output_line)
            self.console.print()
            self._show_status("Processing results...")
        else:
            error_line = self._tool_renderer._render_error(
                tool.error or "Unknown error"
            )
            self._print(error_line)
            self.console.print()
            self._show_status("Handling error...")

    # ─────────────────────────────────────────────────────────────────────
    # Live status with Rich spinner (inline, not sticky)
    # ─────────────────────────────────────────────────────────────────────

    def _start_live_status(self) -> None:
        """Start the Rich Status spinner with initial message."""
        self._show_status("Initializing...")

    def _stop_live_status(self) -> None:
        """Stop and clear any active status spinner."""
        self._stop_status_timer()
        if self._status:
            self._status.stop()
            self._status = None

    def _start_status_timer(self) -> None:
        """Start timer to refresh status bar every second."""
        self._stop_status_timer()
        if self._is_running and self._status:

            def refresh() -> None:
                if self._status and self._is_running:
                    self._status.update(self._build_status_line())
                    self._start_status_timer()

            self._status_timer = threading.Timer(1.0, refresh)
            self._status_timer.daemon = True
            self._status_timer.start()

    def _stop_status_timer(self) -> None:
        """Stop the status refresh timer."""
        if self._status_timer:
            self._status_timer.cancel()
            self._status_timer = None

    def _show_status(self, message: str = "") -> None:
        """Show animated status with Rich spinner inline using fresh console."""
        status_text = self._build_status_line()
        if self._status:
            self._status.update(status_text)
        else:
            self.console.print()
            fresh_console = Console(force_terminal=True)
            self._status = Status(
                status_text,
                spinner="dots",
                spinner_style=THEME["agent_active"],
                console=fresh_console,
                refresh_per_second=4,
            )
            self._status.start()
            self._start_status_timer()

    def _build_status_line(self, message: str = "") -> str:
        """
        Build clean status line matching TASK header style.

        Format: Agent Name  │  elapsed  │  tokens
        """
        if not self._task:
            return ""

        elapsed = time.time() - self._task.start_time
        if elapsed < 60:
            time_str = f"{int(elapsed)}s"
        else:
            time_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

        tokens_in = self._task.token_input
        tokens_out = self._task.token_output

        agent_name = self._current_agent_name or "Agent"

        return (
            f"  [{THEME['agent_active']}]{agent_name}[/]  │  "
            f"[{THEME['muted']}]{time_str}[/]  │  "
            f"[{THEME['muted']}]{tokens_in}[/][dim]↑[/] "
            f"[{THEME['muted']}]{tokens_out}[/][dim]↓[/]"
        )

    def _print_status_bar(self) -> None:
        """Print inline status bar (matches TASK header style)."""
        if not self._task:
            return

        elapsed = self._task.duration
        if elapsed < 60:
            time_str = f"{int(elapsed)}s"
        else:
            time_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"

        tokens_in = self._task.token_input
        tokens_out = self._task.token_output

        agent_name = self._current_agent_name or "Starting"

        agent_tools = "0/0"
        if self._task.active_agent_id:
            agent = self._task.agents.get(self._task.active_agent_id)
            if agent:
                total = len(agent.tools)
                done = sum(1 for t in agent.tools if t.status != "pending")
                agent_tools = f"{done}/{total}"

        total_tools = self._task.total_tools
        global_done = sum(
            1
            for a in self._task.agents.values()
            for t in a.tools
            if t.status != "pending"
        )

        bar = Text()
        bar.append(
            "  ─────────────────────────────────────────────────────────────────\n",
            style=THEME["border"],
        )
        bar.append(f"  {agent_name} ", style=f"bold {THEME['agent_active']}")
        bar.append(f"[{agent_tools}]", style=THEME["muted"])
        bar.append(" │ ", style=THEME["border"])
        bar.append(f"t:{time_str}", style=THEME["muted"])
        bar.append(" │ ", style=THEME["border"])
        bar.append(f"tools:{global_done}/{total_tools}", style=THEME["muted"])
        bar.append(" │ ", style=THEME["border"])
        bar.append(f"tok:{tokens_in}↑{tokens_out}↓", style=THEME["muted"])
        bar.append(
            "\n  ─────────────────────────────────────────────────────────────────",
            style=THEME["border"],
        )

        self.console.print(bar)
        self._flush()

    def _build_status_message(self) -> str:
        """Build the current status message for the spinner."""
        if not self._task:
            return "Initializing..."

        parts = []

        if self._current_agent_name:
            parts.append(f"[bold {THEME['agent_active']}]{self._current_agent_name}[/]")

        agent = None
        if self._task.active_agent_id:
            agent = self._task.agents.get(self._task.active_agent_id)

        if agent:
            pending_tools = [t for t in agent.tools if t.status == "pending"]
            if pending_tools:
                tool = pending_tools[-1]
                parts.append(f"[{THEME['tool_pending']}]⚙ {tool.name}[/]")
            elif agent.status == "thinking":
                parts.append(f"[{THEME['thinking']}]💭 Thinking[/]")
            else:
                parts.append(f"[{THEME['muted']}]Processing[/]")

        elapsed = self._task.duration
        if elapsed < 60:
            time_str = f"{int(elapsed)}s"
        else:
            time_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        parts.append(f"[{THEME['muted']}]{time_str}[/]")

        if self._task.token_input > 0 or self._task.token_output > 0:
            tokens = f"{self._task.token_input}↑ {self._task.token_output}↓"
            parts.append(f"[{THEME['muted']}]{tokens}[/]")

        return " │ ".join(parts) if parts else "Processing..."

    def _render_status_line(self) -> None:
        """Update the live status line."""
        self._update_live_status()

    # ─────────────────────────────────────────────────────────────────────
    # Session log
    # ─────────────────────────────────────────────────────────────────────

    def print_session_log(self) -> None:
        """Print the complete session summary."""
        if not self._task:
            return

        self._print_raw(f"\n[{THEME['border']}]{'═' * 70}[/]")
        self._print_raw(f"[bold {THEME['text']}]  SESSION SUMMARY[/]")
        self._print_raw(f"[{THEME['border']}]{'═' * 70}[/]")

        # Stats
        duration = self._task.duration
        if duration < 60:
            duration_str = f"{int(duration)}s"
        else:
            mins = int(duration // 60)
            secs = int(duration % 60)
            duration_str = f"{mins}m {secs}s"

        success = self._task.total_tools - self._task.failed_tools
        stats = (
            f"  Duration: {duration_str} │ "
            f"Tools: {success}/{self._task.total_tools} │ "
            f"Tokens: {self._task.token_input}↑ {self._task.token_output}↓ │ "
            f"Agents: {len(self._task.agents)}"
        )
        self._print_raw(f"[{THEME['muted']}]{stats}[/]")
        self._print_raw(f"[{THEME['border']}]{'═' * 70}[/]")

    # ─────────────────────────────────────────────────────────────────────
    # Tool explorer
    # ─────────────────────────────────────────────────────────────────────

    def start_tool_explorer(self) -> None:
        """Launch interactive tool explorer."""
        if not self._tool_history:
            self._print_raw(f"[{THEME['muted']}]No tools executed.[/]")
            return

        self.console.print()
        self._print_raw(f"[bold {THEME['text']}]─── Tool Explorer ───[/]")
        self._print_raw(
            f"[{THEME['muted']}]Enter tool number to expand, 'q' to quit[/]"
        )
        self.console.print()

        for idx, tool in enumerate(self._tool_history, 1):
            status_icon = (
                ICONS["success"] if tool["status"] == "success" else ICONS["error"]
            )
            status_color = (
                THEME["tool_success"] if tool["status"] == "success" else THEME["error"]
            )
            self._print_raw(
                f"  [{status_color}]{status_icon}[/] [{THEME['muted']}]{idx}.[/] "
                f"[bold {THEME['text']}]{tool['name']}[/]"
            )

        self.console.print()

        while True:
            try:
                choice = self.console.input(f"[{THEME['text']}]› [/]").strip().lower()
                if choice in ("q", "quit", "exit", ""):
                    break
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(self._tool_history):
                        self._print_tool_detail(self._tool_history[idx])
                    else:
                        self._print_raw(f"[{THEME['warning']}]Invalid number[/]")
            except (EOFError, KeyboardInterrupt):
                break

    def _print_tool_detail(self, tool: Dict[str, Any]) -> None:
        """Print expanded tool details."""
        import json

        self.console.print()
        self._print_raw(f"[bold {THEME['text']}]┌─ {tool['name']} ─┐[/]")

        self._print_raw(f"[{THEME['input']}]│ Input:[/]")
        if tool["input"]:
            try:
                formatted = json.dumps(tool["input"], indent=2, default=str)
                for line in formatted.split("\n"):
                    self._print_raw(f"[{THEME['muted']}]│   [/]{line}")
            except Exception:
                self._print_raw(f"[{THEME['muted']}]│   [/]{tool['input']}")
        else:
            self._print_raw(f"[{THEME['muted']}]│   (none)[/]")

        self._print_raw(f"[{THEME['output']}]│ Output:[/]")
        if tool["output"]:
            output_str = str(tool["output"])
            for line in output_str.split("\n"):
                self._print_raw(f"[{THEME['muted']}]│   [/]{line}")
        elif tool["error"]:
            self._print_raw(f"[{THEME['error']}]│   {tool['error']}[/]")
        else:
            self._print_raw(f"[{THEME['muted']}]│   (none)[/]")

        self._print_raw(f"[{THEME['border']}]└{'─' * 40}┘[/]")
        self.console.print()

    # ─────────────────────────────────────────────────────────────────────
    # Legacy API compatibility
    # ─────────────────────────────────────────────────────────────────────

    def add_log_entry(
        self,
        action_type: ActionType,
        message: str,
        target: Optional[str] = None,
        status: str = "pending",
    ) -> int:
        """Legacy API: Add a log entry."""
        if self._is_running:
            line = Text()
            if status == "error":
                line.append(f"  {ICONS['error']} ", style=f"bold {THEME['error']}")
                line.append(message, style=THEME["error"])
            else:
                line.append(f"  {ICONS['bullet']} ", style=THEME["muted"])
                line.append(message, style=THEME["text"])
            self._print(line)
        return 0

    def update_log_entry(self, idx: int, status: str) -> None:
        """Legacy API: Update a log entry status."""
        pass

    def set_steps(self, current: int, total: int) -> None:
        """Legacy API: Set step progress."""
        pass

    def set_last_result(self, result: str) -> None:
        """Legacy API: Set last result."""
        pass

    def show_human_assistance(self, reason: str, instructions: str) -> None:
        """Legacy API: Show human assistance panel."""
        pass

    def hide_human_assistance(self) -> None:
        """Legacy API: Hide human assistance panel."""
        pass

    def show_command_approval(self, command: str) -> None:
        """Legacy API: Show command approval panel."""
        pass

    def hide_command_approval(self) -> None:
        """Legacy API: Hide command approval panel."""
        pass

    def set_browser_session(self, active: bool, profile: Optional[str] = None) -> None:
        """Legacy API: Set browser session state."""
        pass

    def refresh(self) -> None:
        """Legacy API: Force refresh."""
        self._render_status_line()


# Singleton instance
dashboard = DashboardManager()
console = dashboard.console
