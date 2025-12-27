"""
Enterprise-grade terminal UI with high-performance dashboard.
Single stable dashboard with bright colors and no flickering.
"""

import re
import sys
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Literal, Any, Set
import uuid

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return ANSI_ESCAPE_PATTERN.sub("", text)


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


ACTION_ICONS = {
    ActionType.CLICK: "●",
    ActionType.TYPE: "⌨",
    ActionType.SCROLL: "↕",
    ActionType.OPEN: "◈",
    ActionType.READ: "◉",
    ActionType.SEARCH: "⊙",
    ActionType.NAVIGATE: "→",
    ActionType.ANALYZE: "◐",
    ActionType.EXECUTE: "▸",
    ActionType.PLAN: "◇",
    ActionType.COMPLETE: "✓",
    ActionType.ERROR: "✗",
    ActionType.WEBHOOK: "⚡",
}

THINKING_SPINNER_FRAMES = ["◜", "◠", "◝", "◞", "◡", "◟"]


HIGH_SIGNAL_NAVIGATE_KEYWORDS = (
    "step",
    "navigat",
    "login",
    "click",
    "success",
    "fail",
)

HIGH_SIGNAL_CLICK_KEYWORDS = (
    "button",
    "link",
    "submit",
    "login",
    "sign",
)

THEME = {
    "bg": "#0d1117",
    "fg": "#e6edf3",
    "primary": "#58a6ff",
    "secondary": "#a371f7",
    "accent": "#00ffff",
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    "muted": "#7d8590",
    "surface": "#161b22",
    "border": "#30363d",
    "bright": "#ffffff",
}


@dataclass
class ActionLogEntry:
    """Single entry in the action log with optional nested result."""

    action_type: ActionType
    message: str
    target: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"
    result: Optional[str] = None


@dataclass
class WebhookEvent:
    """Webhook/server event entry."""

    event_type: str
    source: str
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class HierarchicalLogEntry:
    """Log entry with hierarchy context for Agent -> Tool -> Action structure."""

    entry_id: str
    entry_type: Literal["agent", "tool", "action", "error", "input", "output", "thinking"]
    action_type: ActionType
    message: str
    target: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"
    result: Optional[str] = None
    parent_id: Optional[str] = None
    agent_name: Optional[str] = None
    tool_name: Optional[str] = None
    depth: int = 0
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    error_detail: Optional[str] = None


@dataclass
class ActivityState:
    """Central state container for hierarchical activity display."""

    entries: Dict[str, HierarchicalLogEntry] = field(default_factory=dict)
    entry_order: List[str] = field(default_factory=list)
    active_agent_id: Optional[str] = None
    active_tool_id: Optional[str] = None
    error_count: int = 0

    def clear(self) -> None:
        self.entries.clear()
        self.entry_order.clear()
        self.active_agent_id = None
        self.active_tool_id = None
        self.error_count = 0


class LogBatcher:
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

        from . import ui
        dashboard = ui.dashboard

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
    Single stable dashboard with no flickering.
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

        self.console = Console(force_terminal=True)
        self.verbosity = VerbosityLevel.NORMAL
        self._live: Optional[Live] = None
        self._lock = threading.Lock()

        self._task: Optional[str] = None
        self._current_agent: Optional[str] = None
        self._current_action: Optional[str] = None
        self._action_target: Optional[str] = None
        self._step_current = 0
        self._step_total = 0
        self._status = "ready"

        self._action_log: List[ActionLogEntry] = []
        self._max_log_entries = 100

        self._activity = ActivityState()

        self._webhook_events: List[WebhookEvent] = []
        self._max_webhook_events = 4

        self._is_running = False
        self._anim_frame = 0
        self._last_refresh = 0.0
        self._dirty = False
        self._refresh_timer: Optional[threading.Timer] = None

        self._human_assistance_active = False
        self._human_assistance_reason: Optional[str] = None
        self._human_assistance_instructions: Optional[str] = None

        self._command_approval_active = False
        self._command_approval_command: Optional[str] = None

        self._browser_profile: Optional[str] = None
        self._browser_session_active = False

        self._current_thinking: Optional[str] = None
        self._task_start_time: Optional[float] = None
        self._tool_count = 0
        self._tool_success_count = 0

        self._token_input = 0
        self._token_output = 0

        self._printed_entries: Set[str] = set()
        self._header_printed = False
        self._use_native_scroll = True
        self._agent_ids: Dict[str, str] = {}
        self._scroll_region_set = False
        self._tool_history: List[Dict[str, Any]] = []
        self._thinking_spinner_idx = 0
        self._is_thinking = False

    @property
    def is_quiet(self) -> bool:
        """Return True when verbosity is QUIET."""
        return self.verbosity == VerbosityLevel.QUIET

    @property
    def is_verbose(self) -> bool:
        """Return True when verbosity is VERBOSE."""
        return self.verbosity == VerbosityLevel.VERBOSE

    def set_verbosity(self, level: VerbosityLevel) -> None:
        """Set the verbosity level."""
        self.verbosity = level

    @staticmethod
    def _trim_tail(entries: List, max_entries: int) -> List:
        """Trim a list to its last max_entries when it grows too large."""
        if len(entries) > max_entries * 2:
            return entries[-max_entries:]
        return entries

    def _is_raw_tool_call(self, message: str) -> bool:
        """Check if message is a raw tool call that should be filtered."""
        if '{"' in message and '":' in message:
            return True
        if message.count(":") == 1 and message.endswith("}"):
            return True
        return False

    def _is_duplicate_entry(self, entry: ActionLogEntry, idx: int) -> bool:
        """Check if entry is a duplicate of a nearby entry."""
        if idx == 0:
            return False

        for i in range(max(0, idx - 3), idx):
            prev = self._action_log[i]
            if prev.message == entry.message:
                return True
            if entry.message.startswith(
                prev.message.rstrip("...")
            ) or prev.message.startswith(entry.message.rstrip("...")):
                if entry.status == "complete" and prev.status != "complete":
                    return False
                return True
        return False

    def _is_high_signal_entry(self, entry: ActionLogEntry, idx: int = 0) -> bool:
        if entry.status == "error" or entry.action_type == ActionType.ERROR:
            return True

        if self._is_raw_tool_call(entry.message):
            return False

        if self._is_duplicate_entry(entry, idx):
            return False

        high_signal_types = {
            ActionType.COMPLETE,
            ActionType.ERROR,
            ActionType.PLAN,
            ActionType.OPEN,
            ActionType.WEBHOOK,
        }

        if entry.action_type in high_signal_types:
            return True

        if entry.status in {"error", "complete"}:
            return True

        if entry.action_type == ActionType.NAVIGATE:
            msg_lower = entry.message.lower()
            return any(kw in msg_lower for kw in HIGH_SIGNAL_NAVIGATE_KEYWORDS)

        if entry.action_type == ActionType.CLICK:
            msg_lower = entry.message.lower()
            return any(kw in msg_lower for kw in HIGH_SIGNAL_CLICK_KEYWORDS)

        return False

    def _get_filtered_entries(self) -> List[ActionLogEntry]:
        """Get log entries filtered by verbosity level."""
        if self.is_verbose:
            return [
                e
                for i, e in enumerate(self._action_log)
                if not self._is_raw_tool_call(e.message)
            ]

        if self.is_quiet:
            return [e for e in self._action_log if e.status in ("complete", "error")]

        return [
            e
            for i, e in enumerate(self._action_log)
            if self._is_high_signal_entry(e, i)
        ]

    def _build_header(self) -> Panel:
        """Build the compact header section with title and task."""
        title = Text()
        title.append(" ◆ ", style=f"bold {THEME['accent']}")
        title.append("COMPUTER USE AGENT", style=f"bold {THEME['bright']}")

        if self._task:
            title.append("  │  ", style=THEME["border"])
            task_display = (
                self._task[:60] + "..." if len(self._task) > 60 else self._task
            )
            title.append(task_display, style=THEME["fg"])

        return Panel(
            title,
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _build_human_assistance_panel(self) -> Panel:
        """Render the human assistance block."""
        lines: List[Text] = []

        ha_header = Text()
        ha_header.append(" 🤝 ", style=f"bold {THEME['warning']}")
        ha_header.append("HUMAN ASSISTANCE REQUIRED", style=f"bold {THEME['bright']}")
        lines.append(ha_header)
        lines.append(Text(""))

        if self._human_assistance_reason:
            lines.append(Text(" Reason:", style=f"bold {THEME['muted']}"))
            lines.append(Text(f" {self._human_assistance_reason}", style=THEME["fg"]))
            lines.append(Text(""))

        if self._human_assistance_instructions:
            lines.append(Text(" Instructions:", style=f"bold {THEME['muted']}"))
            lines.append(
                Text(f" {self._human_assistance_instructions}", style=THEME["fg"])
            )
            lines.append(Text(""))

        lines.append(Text(" Browser window remains open.", style=THEME["muted"]))
        lines.append(Text(""))

        buttons = Text()
        buttons.append(" ")
        buttons.append("[P]", style=f"bold {THEME['success']}")
        buttons.append(" Proceed  ", style=THEME["fg"])
        buttons.append("[R]", style=f"bold {THEME['primary']}")
        buttons.append(" Retry  ", style=THEME["fg"])
        buttons.append("[S]", style=f"bold {THEME['warning']}")
        buttons.append(" Skip  ", style=THEME["fg"])
        buttons.append("[C]", style=f"bold {THEME['error']}")
        buttons.append(" Cancel", style=THEME["fg"])
        lines.append(buttons)

        return Panel(
            Group(*lines),
            title=f"[{THEME['warning']}]ACTION REQUIRED[/]",
            box=box.ROUNDED,
            border_style=THEME["warning"],
            padding=(0, 1),
        )

    def _build_command_approval_panel(self) -> Panel:
        """Render the command approval block."""
        lines: List[Text] = []

        header = Text()
        header.append(" ⚠ ", style=f"bold {THEME['warning']}")
        header.append("COMMAND REQUIRES APPROVAL", style=f"bold {THEME['bright']}")
        lines.append(header)
        lines.append(Text(""))

        if self._command_approval_command:
            lines.append(Text(" Command:", style=f"bold {THEME['muted']}"))
            cmd_display = self._command_approval_command
            if len(cmd_display) > 80:
                cmd_display = cmd_display[:77] + "..."
            lines.append(Text(f" {cmd_display}", style=f"bold {THEME['warning']}"))
            lines.append(Text(""))

        lines.append(Text(" Select an option:", style=THEME["muted"]))
        lines.append(Text(""))

        buttons = Text()
        buttons.append(" ")
        buttons.append("[1]", style=f"bold {THEME['success']}")
        buttons.append(" Allow once  ", style=THEME["fg"])
        buttons.append("[2]", style=f"bold {THEME['primary']}")
        buttons.append(" Allow for session  ", style=THEME["fg"])
        buttons.append("[3]", style=f"bold {THEME['error']}")
        buttons.append(" Deny & stop", style=THEME["fg"])
        lines.append(buttons)

        return Panel(
            Group(*lines),
            title=f"[{THEME['warning']}]COMMAND APPROVAL[/]",
            box=box.ROUNDED,
            border_style=THEME["warning"],
            padding=(0, 1),
        )

    def _render_hierarchical_entry(self, entry: HierarchicalLogEntry, is_last: bool) -> Text:
        line = Text()
        indent = "  " * entry.depth

        if entry.entry_type == "agent":
            line.append(f"{indent}▸ ", style=f"bold {THEME['secondary']}")
            line.append(entry.message, style=f"bold {THEME['accent']}")
            if entry.entry_id == self._activity.active_agent_id:
                line.append(" [active]", style=THEME["success"])
        elif entry.entry_type == "tool":
            connector = "└─" if is_last else "├─"
            line.append(f"{indent}{connector} ", style=THEME["muted"])
            line.append(entry.message, style=f"bold {THEME['primary']}")
        else:
            connector = "└─" if is_last else "├─"
            icon = ACTION_ICONS.get(entry.action_type, "○")

            if entry.status == "error":
                icon_style = f"bold {THEME['error']}"
                msg_style = f"bold {THEME['error']}"
            elif entry.status == "complete":
                icon_style = THEME["success"]
                msg_style = THEME["fg"]
            else:
                icon_style = THEME["accent"]
                msg_style = THEME["fg"]

            line.append(f"{indent}{connector} ", style=THEME["muted"])
            line.append(f"{icon} ", style=icon_style)
            line.append(entry.message, style=msg_style)

        return line

    def _build_activity(self) -> Panel:
        if self._human_assistance_active:
            return self._build_human_assistance_panel()

        if self._command_approval_active:
            return self._build_command_approval_panel()

        lines = []
        agents = self._group_by_agent()

        for agent_id, agent_data in agents.items():
            agent_lines = self._build_agent_section(agent_id, agent_data)
            lines.extend(agent_lines)

        if not lines:
            if self._current_action:
                spinner_text = Text()
                spinner_text.append(f"  ◐ {self._current_action}", style=f"bold {THEME['bright']}")
                if self._action_target:
                    spinner_text.append(f" → {self._action_target}", style=THEME["warning"])
                spinner = Spinner("dots", text=spinner_text, style=THEME["accent"])
                lines.append(spinner)
            else:
                lines.append(Text("  Waiting for activity...", style=THEME["muted"]))

        if self._webhook_events:
            lines.append(Text(""))
            for event in self._webhook_events[-self._max_webhook_events:]:
                event_line = Text()
                event_line.append("  ⚡ ", style=THEME["warning"])
                event_line.append(f"{event.source}: ", style=THEME["accent"])
                event_line.append(event.message, style=THEME["fg"])
                lines.append(event_line)

        return Panel(
            Group(*lines),
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 1),
        )

    def _group_by_agent(self) -> Dict[str, Dict]:
        """Group all entries by agent, then by tool, preserving thinking entries."""
        agents: Dict[str, Dict] = {}

        for entry_id in self._activity.entry_order:
            entry = self._activity.entries.get(entry_id)
            if not entry:
                continue

            if entry.entry_type == "agent":
                agents[entry_id] = {"entry": entry, "tools": {}, "items": []}
            elif entry.entry_type == "thinking":
                agent_id = entry.parent_id
                if agent_id and agent_id in agents:
                    agents[agent_id]["items"].append(("thinking", entry))
            elif entry.entry_type == "tool":
                agent_id = entry.parent_id
                if agent_id and agent_id in agents:
                    agents[agent_id]["tools"][entry_id] = {"entry": entry, "children": []}
                    agents[agent_id]["items"].append(("tool", entry_id))
            else:
                tool_id = entry.parent_id
                for agent_id, agent_data in agents.items():
                    if tool_id in agent_data["tools"]:
                        agent_data["tools"][tool_id]["children"].append(entry)
                        break

        return agents

    def _build_agent_section(self, agent_id: str, agent_data: Dict) -> List:
        """Build lines for an agent section with thinking + tools in order."""
        agent_entry = agent_data["entry"]
        tools = agent_data["tools"]
        items = agent_data.get("items", [])
        is_active = agent_id == self._activity.active_agent_id

        lines: List = []

        if is_active:
            header = Text()
            header.append("● ", style=f"bold {THEME['success']}")
            header.append(agent_entry.message, style=f"bold {THEME['accent']}")
            header.append(" ACTIVE", style=f"bold {THEME['success']}")
            lines.append(header)
        else:
            header = Text()
            header.append("○ ", style=THEME["muted"])
            header.append(agent_entry.message, style=f"bold {THEME['accent']}")
            lines.append(header)

        if not items:
            if is_active:
                if self._current_thinking:
                    thinking_line = Text()
                    thinking_line.append("  > ", style=THEME["secondary"])
                    thinking_line.append(self._current_thinking, style=f"italic {THEME['fg']}")
                    lines.append(thinking_line)
                spinner = Spinner("dots", text=Text("  Thinking...", style=THEME["muted"]), style=THEME["accent"])
                lines.append(spinner)
            else:
                lines.append(Text("  Waiting...", style=THEME["muted"]))
        else:
            for item_type, item_data in items:
                if item_type == "thinking":
                    thinking_line = Text()
                    thinking_line.append("  > ", style=THEME["secondary"])
                    thinking_line.append(item_data.message, style=f"italic {THEME['muted']}")
                    lines.append(thinking_line)
                elif item_type == "tool":
                    tool_data = tools.get(item_data)
                    if tool_data:
                        tool_lines = self._build_tool_section(tool_data)
                        lines.extend(tool_lines)

            if is_active:
                has_pending = any(
                    tools.get(td, {}).get("entry") and
                    tools.get(td, {}).get("entry").status == "pending"
                    for it, td in items if it == "tool"
                )
                if has_pending:
                    spinner = Spinner("dots", text=Text("  Executing...", style=THEME["muted"]), style=THEME["accent"])
                    lines.append(spinner)

        lines.append(Text(""))
        return lines

    def _build_tool_section(self, tool_data: Dict) -> List:
        """Build compact tool display with inline input/output."""
        tool_entry = tool_data["entry"]
        children = tool_data["children"]
        lines = []

        if tool_entry.status == "pending":
            status_icon = "◐"
            status_style = THEME["accent"]
        elif tool_entry.status == "complete":
            status_icon = "✓"
            status_style = THEME["success"]
        else:
            status_icon = "✗"
            status_style = THEME["error"]

        header = Text()
        header.append(f"  {status_icon} ", style=f"bold {status_style}")
        header.append(tool_entry.message, style=f"bold {THEME['primary']}")
        lines.append(header)

        input_entries = [c for c in children if c.entry_type == "input"]
        for entry in input_entries:
            input_line = Text()
            input_line.append("     → ", style=THEME["warning"])
            input_line.append(entry.message, style=THEME["fg"])
            lines.append(input_line)

        output_entries = [c for c in children if c.entry_type == "output"]
        for entry in output_entries:
            output_line = Text()
            output_line.append("     ← ", style=THEME["success"])
            output_line.append(entry.message, style=THEME["fg"])
            lines.append(output_line)

        error_entries = [c for c in children if c.entry_type == "error"]
        for entry in error_entries:
            error_line = Text()
            error_line.append("     ✗ ", style=f"bold {THEME['error']}")
            error_line.append(entry.message, style=f"bold {THEME['error']}")
            lines.append(error_line)

        result_entries = [c for c in children if c.entry_type == "action" and c.status in ("complete", "error")]
        for entry in result_entries:
            result_line = Text()
            result_line.append("     ", style=THEME["muted"])
            if entry.status == "error":
                result_line.append(entry.message, style=f"bold {THEME['error']}")
            else:
                result_line.append(entry.message, style=THEME["muted"])
            lines.append(result_line)

        return lines

    def _is_high_signal_entry_h(self, entry: HierarchicalLogEntry) -> bool:
        if entry.status == "error" or entry.action_type == ActionType.ERROR:
            return True

        if '{"' in entry.message and '":' in entry.message:
            return False

        high_signal_types = {
            ActionType.COMPLETE,
            ActionType.ERROR,
            ActionType.PLAN,
            ActionType.OPEN,
            ActionType.WEBHOOK,
        }
        if entry.action_type in high_signal_types:
            return True

        if entry.action_type == ActionType.NAVIGATE:
            msg_lower = entry.message.lower()
            return any(kw in msg_lower for kw in HIGH_SIGNAL_NAVIGATE_KEYWORDS)

        if entry.action_type == ActionType.CLICK:
            msg_lower = entry.message.lower()
            return any(kw in msg_lower for kw in HIGH_SIGNAL_CLICK_KEYWORDS)

        return False

    def _build_status_bar(self) -> Panel:
        """Build status bar with agent, action, time, and stats."""
        status = Text()

        if self._current_agent:
            status.append(" ● ", style=f"bold {THEME['success']}")
            status.append(self._current_agent, style=f"bold {THEME['accent']}")
        else:
            status.append(" ○ ", style=THEME["muted"])
            status.append("Ready", style=THEME["muted"])

        if self._current_action:
            status.append("  ▸ ", style=THEME["accent"])
            action_text = self._current_action[:25]
            if len(self._current_action) > 25:
                action_text += "..."
            status.append(action_text, style=f"dim {THEME['fg']}")

        status.append("  │  ", style=THEME["border"])

        if self._task_start_time:
            elapsed = time.time() - self._task_start_time
            if elapsed < 60:
                time_str = f"{int(elapsed)}s"
            else:
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                time_str = f"{mins}m {secs}s"
            status.append("⏱ ", style=THEME["accent"])
            status.append(time_str, style=f"bold {THEME['fg']}")
            status.append("  │  ", style=THEME["border"])

        if self._tool_count > 0:
            status.append("✓ ", style=THEME["success"])
            status.append(f"{self._tool_success_count}/{self._tool_count}", style=f"bold {THEME['fg']}")
            error_count = self._tool_count - self._tool_success_count
            if error_count > 0:
                status.append(" ", style=THEME["fg"])
                status.append(f"{error_count}✗", style=f"bold {THEME['error']}")
            status.append("  │  ", style=THEME["border"])

        if self._token_input > 0 or self._token_output > 0:
            total_tokens = self._token_input + self._token_output
            if total_tokens >= 1000:
                token_str = f"{total_tokens/1000:.0f}k"
            else:
                token_str = str(total_tokens)
            status.append("◇ ", style=THEME["secondary"])
            status.append(token_str, style=f"bold {THEME['fg']}")
            status.append("  │  ", style=THEME["border"])

        status.append("ESC", style=f"bold {THEME['warning']}")
        status.append(" stop", style=THEME["muted"])

        return Panel(
            status,
            box=box.ROUNDED,
            border_style=THEME["border"],
            padding=(0, 0),
        )

    def _build_dashboard(self) -> Layout:
        """Build the full-screen dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="activity", ratio=1),
            Layout(name="status_bar", size=3),
        )

        layout["header"].update(self._build_header())
        layout["activity"].update(self._build_activity())
        layout["status_bar"].update(self._build_status_bar())

        return layout

    def start_dashboard(self) -> None:
        """Start the dashboard display with native scrolling."""
        if self.is_quiet:
            return

        if self._is_running:
            return

        self._is_running = True
        self._dirty = True
        self._printed_entries.clear()
        self._header_printed = False

        if self._use_native_scroll:
            self._render_sticky_footer()
            self._start_periodic_refresh()
        else:
            self._live = Live(
                self._build_dashboard(),
                console=self.console,
                refresh_per_second=8,
                screen=True,
                transient=False,
            )
            self._live.start()
            self._start_periodic_refresh()

    def stop_dashboard(self, print_log: bool = True, cancelled: bool = False) -> None:
        """Stop the live dashboard display and optionally print session log."""
        if not self._is_running:
            return

        self._is_running = False

        if self._refresh_timer:
            self._refresh_timer.cancel()
            self._refresh_timer = None

        if self._use_native_scroll:
            self._clear_sticky_footer()
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

        if print_log and self._activity.entries and not cancelled:
            self.console.print()
            self.print_session_log()

        if self._tool_history and not cancelled:
            try:
                explore = self.console.input(
                    f"\n[{THEME['muted']}]Press Enter to explore tools, or 'q' to skip: [/]"
                ).strip().lower()
                if explore != "q":
                    self.start_tool_explorer()
            except (EOFError, KeyboardInterrupt):
                pass

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _start_periodic_refresh(self) -> None:
        """Start periodic refresh timer for elapsed time updates."""
        if self._refresh_timer is not None:
            return
        interval = 0.15 if self._is_thinking else 0.5
        self._refresh_timer = threading.Timer(interval, self._periodic_refresh)
        self._refresh_timer.daemon = True
        self._refresh_timer.start()

    def _periodic_refresh(self) -> None:
        """Periodic refresh for elapsed time and status updates."""
        self._refresh_timer = None
        if not self._is_running:
            return

        if self._use_native_scroll:
            self._print_new_entries()
            self._render_sticky_footer()
        else:
            self._mark_dirty()
            self._do_refresh()

        self._start_periodic_refresh()

    def refresh(self) -> None:
        self._dirty = True
        self._do_refresh()

    def _do_refresh(self) -> None:
        if not self._is_running:
            return

        if self._use_native_scroll:
            self._print_new_entries()
            return

        if not self._live:
            return
        if not self._dirty:
            return

        self._dirty = False
        self._last_refresh = time.time()

        with self._lock:
            try:
                self._live.update(self._build_dashboard())
            except Exception:
                pass

    def _force_refresh(self) -> None:
        if not self._is_running:
            return
        if self._use_native_scroll:
            self._print_new_entries()
            return
        if not self._live:
            return
        self._dirty = False
        self._last_refresh = time.time()
        with self._lock:
            try:
                self._live.update(self._build_dashboard())
            except Exception:
                pass

    def _print_header(self) -> None:
        """Print the task header once at the start of native scroll mode."""
        if self._header_printed:
            return
        self._header_printed = True

        self.console.print()
        header = Text()
        header.append(" ◆ ", style=f"bold {THEME['accent']}")
        header.append("COMPUTER USE AGENT", style=f"bold {THEME['bright']}")

        if self._task:
            header.append("  │  ", style=THEME["border"])
            task_display = self._task[:70] + "..." if len(self._task) > 70 else self._task
            header.append(task_display, style=THEME["fg"])

        self.console.print(header)
        self.console.print(f"[{THEME['muted']}]{'─' * 60}[/]")
        self.console.print()

    def _print_new_entries(self) -> None:
        """Print only new entries to console (goes to scrollback)."""
        with self._lock:
            agents = self._group_by_agent()
            has_new_content = False

            for agent_id, agent_data in agents.items():
                agent_entry = agent_data["entry"]
                agent_header_key = f"agent_header:{agent_entry.agent_name}"

                if agent_header_key in self._printed_entries:
                    if self._print_new_tools_for_agent(agent_id, agent_data):
                        has_new_content = True
                    continue

                if not has_new_content:
                    sys.stdout.write("\r\x1b[2K")
                    sys.stdout.flush()
                    has_new_content = True

                self._printed_entries.add(agent_header_key)

                self.console.print()
                header = Text()
                header.append("● ", style=f"bold {THEME['success']}")
                header.append(agent_entry.message, style=f"bold {THEME['accent']}")
                self.console.print(header)

                self._print_new_tools_for_agent(agent_id, agent_data)

    def _print_new_tools_for_agent(self, agent_id: str, agent_data: Dict) -> bool:
        """Print new tools and their children for an agent. Returns True if anything printed."""
        items = agent_data.get("items", [])
        tools = agent_data["tools"]
        printed = False

        for item_type, item_data in items:
            if item_type == "thinking":
                continue

            elif item_type == "tool":
                tool_id = item_data
                tool_data = tools.get(tool_id)
                if not tool_data:
                    continue

                tool_entry = tool_data["entry"]
                children = tool_data["children"]

                tool_key = f"tool:{tool_id}"
                if tool_key not in self._printed_entries:
                    if not printed:
                        sys.stdout.write("\r\x1b[2K")
                        sys.stdout.flush()
                        printed = True
                    self._printed_entries.add(tool_key)
                    self._print_tool_entry(tool_entry)

                for child in children:
                    child_key = f"child:{child.entry_id}"
                    if child_key in self._printed_entries:
                        continue
                    if not printed:
                        sys.stdout.write("\r\x1b[2K")
                        sys.stdout.flush()
                        printed = True
                    self._printed_entries.add(child_key)
                    self._print_child_entry(child)

                if tool_entry.status in ("complete", "error"):
                    status_key = f"status:{tool_id}:{tool_entry.status}"
                    if status_key not in self._printed_entries:
                        if not printed:
                            sys.stdout.write("\r\x1b[2K")
                            sys.stdout.flush()
                            printed = True
                        self._printed_entries.add(status_key)
                        self._print_tool_completion(tool_entry)

        return printed

    def _print_tool_entry(self, tool_entry: HierarchicalLogEntry) -> None:
        """Print a tool entry line."""
        status_icon = "◐"
        status_style = THEME["accent"]
        if tool_entry.status == "complete":
            status_icon = "✓"
            status_style = THEME["success"]
        elif tool_entry.status == "error":
            status_icon = "✗"
            status_style = THEME["error"]

        line = Text()
        line.append(f"  {status_icon} ", style=f"bold {status_style}")
        line.append(tool_entry.message, style=f"bold {THEME['primary']}")
        self.console.print(line)

    def _print_child_entry(self, child: HierarchicalLogEntry) -> None:
        """Print a child entry (input/output/error)."""
        if child.entry_type == "input":
            line = Text()
            line.append("     → ", style=THEME["warning"])
            line.append(child.message, style=THEME["fg"])
            self.console.print(line)
        elif child.entry_type == "output":
            line = Text()
            line.append("     ← ", style=THEME["success"])
            line.append(child.message, style=THEME["fg"])
            self.console.print(line)
        elif child.entry_type == "error":
            line = Text()
            line.append("     ✗ ", style=f"bold {THEME['error']}")
            line.append(child.message, style=f"bold {THEME['error']}")
            self.console.print(line)
        elif child.entry_type == "action" and child.status in ("complete", "error"):
            line = Text()
            line.append("     ", style=THEME["muted"])
            if child.status == "error":
                line.append(child.message, style=f"bold {THEME['error']}")
            else:
                line.append(child.message, style=THEME["muted"])
            self.console.print(line)

    def _print_tool_completion(self, tool_entry: HierarchicalLogEntry) -> None:
        """Print status update for a completed/failed tool."""
        if tool_entry.status == "complete":
            line = Text()
            line.append("     ✓ ", style=f"bold {THEME['success']}")
            line.append("completed", style=THEME["success"])
            self.console.print(line)
        elif tool_entry.status == "error":
            line = Text()
            line.append("     ✗ ", style=f"bold {THEME['error']}")
            line.append("failed", style=THEME["error"])
            self.console.print(line)

    def _format_elapsed(self) -> str:
        """Format elapsed time for display."""
        if not self._task_start_time:
            return "0s"
        elapsed = time.time() - self._task_start_time
        if elapsed < 60:
            return f"{int(elapsed)}s"
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        return f"{mins}m {secs}s"

    def _setup_scroll_region(self) -> None:
        pass

    def _reset_scroll_region(self) -> None:
        pass

    def _render_sticky_footer(self) -> None:
        """Print status inline after content."""
        if not sys.stdout.isatty():
            return

        elapsed = self._format_elapsed()
        agent = self._current_agent or "Ready"

        parts = [agent, f"⏱ {elapsed}"]

        if self._tool_count > 0:
            parts.append(f"✓ {self._tool_success_count}/{self._tool_count}")

        if self._token_input + self._token_output > 0:
            total = self._token_input + self._token_output
            parts.append(f"◇ {total // 1000}k" if total >= 1000 else f"◇ {total}")

        status = "  │  ".join(parts)

        with self._lock:
            sys.stdout.write(f"\r\x1b[2K\x1b[2m{status}\x1b[0m")
            sys.stdout.flush()

    def _clear_sticky_footer(self) -> None:
        """Clear the inline status line."""
        with self._lock:
            sys.stdout.write("\r\x1b[2K")
            sys.stdout.flush()

    def set_task(self, task: str) -> None:
        self._task = task
        self._status = "working"
        self._action_log = []
        self._activity.clear()
        self._printed_entries.clear()
        self._task_start_time = time.time()
        self._tool_count = 0
        self._tool_success_count = 0
        self._current_thinking = None
        self._token_input = 0
        self._token_output = 0
        self._agent_ids.clear()
        self._tool_history.clear()
        self._mark_dirty()

    def set_agent(self, agent_name: str) -> None:
        if self._current_agent == agent_name:
            return

        if agent_name in self._agent_ids:
            self._activity.active_agent_id = self._agent_ids[agent_name]
            self._activity.active_tool_id = None
            self._current_agent = agent_name
            self._mark_dirty()
            return

        agent_id = str(uuid.uuid4())
        self._agent_ids[agent_name] = agent_id
        entry = HierarchicalLogEntry(
            entry_id=agent_id,
            entry_type="agent",
            action_type=ActionType.EXECUTE,
            message=agent_name,
            agent_name=agent_name,
            depth=0,
        )
        self._activity.entries[agent_id] = entry
        self._activity.entry_order.append(agent_id)
        self._activity.active_agent_id = agent_id
        self._activity.active_tool_id = None
        self._current_agent = agent_name
        self._mark_dirty()

    def set_action(
        self,
        action: str,
        target: Optional[str] = None,
    ) -> None:
        clean_action = strip_ansi(action)
        clean_target = strip_ansi(target) if target else None

        if clean_action == "Thinking":
            self._is_thinking = True
            if self._refresh_timer:
                self._refresh_timer.cancel()
                self._refresh_timer = None
            self._start_periodic_refresh()
            self._render_sticky_footer()
            return

        self._is_thinking = False

        if self._activity.active_agent_id and clean_action != self._current_action:
            tool_id = str(uuid.uuid4())
            entry = HierarchicalLogEntry(
                entry_id=tool_id,
                entry_type="tool",
                action_type=ActionType.EXECUTE,
                message=clean_action,
                target=clean_target,
                agent_name=self._current_agent,
                tool_name=clean_action,
                parent_id=self._activity.active_agent_id,
                depth=1,
            )
            self._activity.entries[tool_id] = entry
            self._activity.entry_order.append(tool_id)
            self._activity.active_tool_id = tool_id

        self._current_action = clean_action
        self._action_target = clean_target
        self._mark_dirty()

    def clear_action(self) -> None:
        self._current_action = None
        self._action_target = None
        self._activity.active_tool_id = None
        self._mark_dirty()

    def set_thinking(self, thought: str) -> None:
        """Set the current LLM reasoning/thought for display."""
        if not thought:
            return
        clean_thought = strip_ansi(thought).strip()
        if not clean_thought:
            return

        self._current_thinking = clean_thought

        if self._use_native_scroll and self._is_running:
            thinking_key = f"inline_thought:{hash(clean_thought[:100])}"
            if thinking_key not in self._printed_entries:
                self._printed_entries.add(thinking_key)
                with self._lock:
                    line = Text()
                    line.append("  > ", style=THEME["secondary"])
                    line.append(clean_thought, style=f"italic {THEME['muted']}")
                    self.console.print(line)

        self._mark_dirty()

    def update_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Update token usage counters."""
        self._token_input = input_tokens
        self._token_output = output_tokens
        self._mark_dirty()

    def set_last_result(self, result: str) -> None:
        """Set the result on the most recent log entry for hierarchical display."""
        if self._action_log:
            self._action_log[-1].result = strip_ansi(result)
            self._mark_dirty()

    def set_steps(self, current: int, total: int) -> None:
        """Set the step progress."""
        self._step_current = current
        self._step_total = total
        self._mark_dirty()

    def add_log_entry(
        self,
        action_type: ActionType,
        message: str,
        target: Optional[str] = None,
        status: str = "pending",
    ) -> int:
        clean_message = strip_ansi(message)
        clean_target = strip_ansi(target) if target else None

        entry = ActionLogEntry(
            action_type=action_type,
            message=clean_message,
            target=clean_target,
            status=status,
        )
        self._action_log.append(entry)
        self._action_log = self._trim_tail(self._action_log, self._max_log_entries)

        entry_id = str(uuid.uuid4())
        parent_id = self._activity.active_tool_id or self._activity.active_agent_id
        depth = 2 if self._activity.active_tool_id else (1 if self._activity.active_agent_id else 0)

        h_entry = HierarchicalLogEntry(
            entry_id=entry_id,
            entry_type="error" if status == "error" else "action",
            action_type=action_type,
            message=clean_message,
            target=clean_target,
            status=status,
            parent_id=parent_id,
            agent_name=self._current_agent,
            tool_name=self._current_action,
            depth=depth,
        )
        self._activity.entries[entry_id] = h_entry
        self._activity.entry_order.append(entry_id)

        if status == "error" or action_type == ActionType.ERROR:
            self._activity.error_count += 1

        self._mark_dirty()
        return len(self._action_log) - 1

    def update_log_entry(self, idx: int, status: str) -> None:
        if 0 <= idx < len(self._action_log):
            self._action_log[idx].status = status
            if idx < len(self._activity.entry_order):
                entry_id = self._activity.entry_order[idx]
                if entry_id in self._activity.entries:
                    old_status = self._activity.entries[entry_id].status
                    self._activity.entries[entry_id].status = status
                    if status == "error" and old_status != "error":
                        self._activity.error_count += 1
            self._mark_dirty()

    def log_tool_start(self, tool_name: str, tool_input: Any) -> str:
        """Log tool execution start with input parameters."""
        self._tool_count += 1

        if self._current_thinking:
            thinking_id = str(uuid.uuid4())
            thinking_entry = HierarchicalLogEntry(
                entry_id=thinking_id,
                entry_type="thinking",
                action_type=ActionType.PLAN,
                message=self._current_thinking,
                parent_id=self._activity.active_agent_id,
                agent_name=self._current_agent,
                depth=1,
                status="complete",
            )
            self._activity.entries[thinking_id] = thinking_entry
            self._activity.entry_order.append(thinking_id)
            self._current_thinking = None

        tool_id = str(uuid.uuid4())
        tool_entry = HierarchicalLogEntry(
            entry_id=tool_id,
            entry_type="tool",
            action_type=ActionType.EXECUTE,
            message=tool_name,
            agent_name=self._current_agent,
            tool_name=tool_name,
            parent_id=self._activity.active_agent_id,
            depth=1,
            status="pending",
        )
        self._activity.entries[tool_id] = tool_entry
        self._activity.entry_order.append(tool_id)
        self._activity.active_tool_id = tool_id

        input_id = str(uuid.uuid4())
        input_str = self._format_tool_input(tool_input)
        input_data = tool_input if isinstance(tool_input, dict) else {"value": tool_input}
        input_entry = HierarchicalLogEntry(
            entry_id=input_id,
            entry_type="input",
            action_type=ActionType.ANALYZE,
            message=input_str,
            parent_id=tool_id,
            depth=2,
            status="complete",
            tool_input=input_data,
        )
        self._activity.entries[input_id] = input_entry
        self._activity.entry_order.append(input_id)

        self._current_action = tool_name
        self._is_thinking = False
        self._mark_dirty()

        self._tool_history.append({
            "id": tool_id,
            "name": tool_name,
            "input": tool_input,
            "output": None,
            "error": None,
            "status": "pending",
            "timestamp": time.time(),
        })

        if self._use_native_scroll and self._is_running:
            self._print_new_entries()
            self._render_sticky_footer()

        return tool_id

    def get_pending_tool_id(self, tool_name: str = None) -> Optional[str]:
        """Find the most recent pending tool entry, optionally matching by name."""
        for entry_id in reversed(self._activity.entry_order):
            entry = self._activity.entries.get(entry_id)
            if entry and entry.entry_type == "tool" and entry.status == "pending":
                if tool_name is None or entry.tool_name == tool_name:
                    return entry_id
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
        """Log tool completion with output or error."""
        if not tool_id or tool_id not in self._activity.entries:
            return

        if success:
            self._tool_success_count += 1

        tool_entry = self._activity.entries[tool_id]

        output_id = str(uuid.uuid4())
        if success:
            output_parts = []
            if method_used:
                output_parts.append(f"method={method_used}")
            if confidence > 0:
                output_parts.append(f"confidence={confidence:.2f}")
            output_str = " │ ".join(output_parts) if output_parts else "success"

            output_entry = HierarchicalLogEntry(
                entry_id=output_id,
                entry_type="output",
                action_type=ActionType.COMPLETE,
                message=output_str,
                parent_id=tool_id,
                depth=2,
                status="complete",
                tool_output=data,
            )
        else:
            error_msg = error or "Unknown error"
            output_entry = HierarchicalLogEntry(
                entry_id=output_id,
                entry_type="error",
                action_type=ActionType.ERROR,
                message=error_msg,
                parent_id=tool_id,
                depth=2,
                status="error",
                error_detail=error_msg,
            )
            self._activity.error_count += 1

        self._activity.entries[output_id] = output_entry
        self._activity.entry_order.append(output_id)

        tool_entry.status = "complete" if success else "error"

        if action_taken:
            result_id = str(uuid.uuid4())
            icon = "✓" if success else "✗"
            result_entry = HierarchicalLogEntry(
                entry_id=result_id,
                entry_type="action",
                action_type=ActionType.COMPLETE if success else ActionType.ERROR,
                message=f"{icon} {action_taken}",
                parent_id=tool_id,
                depth=2,
                status="complete" if success else "error",
            )
            self._activity.entries[result_id] = result_entry
            self._activity.entry_order.append(result_id)

        self._activity.active_tool_id = None

        for tool in self._tool_history:
            if tool["id"] == tool_id:
                tool["output"] = action_taken if action_taken else data
                tool["error"] = error
                tool["status"] = "complete" if success else "error"
                break

        self._mark_dirty()

        if self._use_native_scroll and self._is_running:
            self._print_new_entries()
            self._render_sticky_footer()

    def _format_tool_input(self, tool_input: Any) -> str:
        """Format tool input for display (truncated)."""
        if isinstance(tool_input, dict):
            parts = []
            for k, v in list(tool_input.items())[:4]:
                if isinstance(v, str):
                    v_display = v[:30] + "..." if len(v) > 30 else v
                    parts.append(f'{k}="{v_display}"')
                else:
                    parts.append(f"{k}={v}")
            return ", ".join(parts)
        elif isinstance(tool_input, str):
            return tool_input[:60] + "..." if len(tool_input) > 60 else tool_input
        else:
            return str(tool_input)[:60]

    def add_webhook_event(self, event_type: str, source: str, message: str) -> None:
        """Add a webhook/server event."""
        event = WebhookEvent(
            event_type=event_type,
            source=source,
            message=message,
        )
        self._webhook_events.append(event)
        self._webhook_events = self._trim_tail(
            self._webhook_events, self._max_webhook_events
        )

        self._mark_dirty()

    def complete_task(self, success: bool = True) -> None:
        """Mark the current task as complete."""
        self._status = "complete" if success else "error"
        self._current_action = None
        self._action_target = None

        status_type = ActionType.COMPLETE if success else ActionType.ERROR
        status_msg = "Task completed successfully" if success else "Task failed"
        self.add_log_entry(
            status_type, status_msg, status="complete" if success else "error"
        )
        self._mark_dirty()

    def print_session_log(self) -> None:
        """Print the complete session log with hierarchical entries."""
        self.console.print()

        self.console.print(
            f"  [{THEME['accent']}]◆[/] [{THEME['bright']}]Session Log[/]"
        )
        self.console.print(f"  [{THEME['muted']}]{'─' * 50}[/]")

        if self._task:
            self.console.print(f"  [{THEME['muted']}]Task:[/] {self._task}")
            self.console.print()

        agents = self._group_by_agent()
        for agent_id, agent_data in agents.items():
            agent_entry = agent_data["entry"]
            tools = agent_data["tools"]
            items = agent_data.get("items", [])

            self.console.print(
                f"  [{THEME['accent']}]●[/] [{THEME['accent']}]{agent_entry.message}[/]"
            )

            for item_type, item_data in items:
                if item_type == "thinking":
                    thought = item_data.message[:100]
                    if len(item_data.message) > 100:
                        thought += "..."
                    self.console.print(
                        f"    [{THEME['muted']}]>[/] [{THEME['muted']}italic]{thought}[/]"
                    )
                elif item_type == "tool":
                    tool_data = tools.get(item_data)
                    if tool_data:
                        tool_entry = tool_data["entry"]
                        children = tool_data["children"]

                        if tool_entry.status == "complete":
                            icon = "✓"
                            icon_style = THEME["success"]
                        elif tool_entry.status == "error":
                            icon = "✗"
                            icon_style = THEME["error"]
                        else:
                            icon = "○"
                            icon_style = THEME["muted"]

                        self.console.print(
                            f"    [{icon_style}]{icon}[/] [{THEME['primary']}]{tool_entry.message}[/]"
                        )

                        for child in children:
                            if child.entry_type == "input":
                                self.console.print(
                                    f"      [{THEME['warning']}]→[/] [{THEME['fg']}]{child.message}[/]"
                                )
                            elif child.entry_type == "output":
                                self.console.print(
                                    f"      [{THEME['success']}]←[/] [{THEME['fg']}]{child.message}[/]"
                                )
                            elif child.entry_type == "error":
                                self.console.print(
                                    f"      [{THEME['error']}]✗[/] [{THEME['error']}]{child.message}[/]"
                                )

            self.console.print()

        self.console.print(f"  [{THEME['muted']}]{'─' * 50}[/]")

        stats_parts = []
        if self._task_start_time:
            elapsed = int(time.time() - self._task_start_time)
            mins, secs = divmod(elapsed, 60)
            if mins > 0:
                stats_parts.append(f"Duration: {mins}m {secs}s")
            else:
                stats_parts.append(f"Duration: {secs}s")
        if self._tool_count > 0:
            stats_parts.append(f"Tools: {self._tool_success_count}/{self._tool_count}")
        if self._token_input > 0 or self._token_output > 0:
            stats_parts.append(f"Tokens: {self._token_input}→{self._token_output}")
        if stats_parts:
            stats_line = " │ ".join(stats_parts)
            self.console.print(f"  [{THEME['muted']}]{stats_line}[/]")

        self.console.print()

    def show_human_assistance(self, reason: str, instructions: str) -> None:
        """Show human assistance panel in the dashboard."""
        self._human_assistance_active = True
        self._human_assistance_reason = reason
        self._human_assistance_instructions = instructions
        self._mark_dirty()

    def hide_human_assistance(self) -> None:
        """Hide the human assistance panel."""
        self._human_assistance_active = False
        self._human_assistance_reason = None
        self._human_assistance_instructions = None
        self._mark_dirty()

    def show_command_approval(self, command: str) -> None:
        """Show command approval panel in the dashboard."""
        self._command_approval_active = True
        self._command_approval_command = command
        self._mark_dirty()

    def hide_command_approval(self) -> None:
        """Hide the command approval panel."""
        self._command_approval_active = False
        self._command_approval_command = None
        self._mark_dirty()

    def set_browser_session(self, active: bool, profile: Optional[str] = None) -> None:
        """Set browser session state for status bar display."""
        self._browser_session_active = active
        self._browser_profile = profile
        self._mark_dirty()

    def start_tool_explorer(self) -> None:
        """Launch interactive tool explorer after task completion."""
        if not self._tool_history:
            self.console.print(f"[{THEME['muted']}]No tools executed.[/]")
            return

        self.console.print()
        self.console.print(f"[bold {THEME['accent']}]─── Tool Explorer ───[/]")
        self.console.print(f"[{THEME['muted']}]Enter tool number to expand, 'q' to quit[/]")
        self.console.print()

        for idx, tool in enumerate(self._tool_history, 1):
            status_icon = "✓" if tool["status"] == "complete" else "✗"
            status_color = THEME["success"] if tool["status"] == "complete" else THEME["error"]
            self.console.print(
                f"  [{status_color}]{status_icon}[/] [{THEME['muted']}]{idx}.[/] "
                f"[bold {THEME['primary']}]{tool['name']}[/]"
            )

        self.console.print()

        while True:
            try:
                choice = self.console.input(f"[{THEME['accent']}]› [/]").strip().lower()
                if choice in ("q", "quit", "exit", ""):
                    break
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(self._tool_history):
                        self._print_tool_detail(self._tool_history[idx])
                    else:
                        self.console.print(f"[{THEME['warning']}]Invalid number[/]")
            except (EOFError, KeyboardInterrupt):
                break

    def _print_tool_detail(self, tool: Dict[str, Any]) -> None:
        """Print expanded tool details with full input/output."""
        self.console.print()
        self.console.print(f"[bold {THEME['primary']}]┌─ {tool['name']} ─┐[/]")

        self.console.print(f"[{THEME['warning']}]│ Input:[/]")
        if tool["input"]:
            self._print_json_pretty(tool["input"], prefix="│   ")
        else:
            self.console.print(f"[{THEME['muted']}]│   (none)[/]")

        self.console.print(f"[{THEME['success']}]│ Output:[/]")
        if tool["output"]:
            if isinstance(tool["output"], str):
                for line in tool["output"].split("\n"):
                    if line.strip():
                        self.console.print(f"[{THEME['fg']}]│   {line}[/]")
            else:
                self._print_json_pretty(tool["output"], prefix="│   ")
        elif tool["error"]:
            self.console.print(f"[{THEME['error']}]│   {tool['error']}[/]")
        else:
            self.console.print(f"[{THEME['muted']}]│   (none)[/]")

        self.console.print(f"[{THEME['border']}]└{'─' * 40}┘[/]")
        self.console.print()

    def _print_json_pretty(self, data: Any, prefix: str = "") -> None:
        """Pretty print JSON/dict data with syntax highlighting."""
        import json
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and len(value) > 80:
                    value = value[:77] + "..."
                self.console.print(
                    f"[{THEME['muted']}]{prefix}[/][{THEME['accent']}]{key}[/]: {value}"
                )
        elif isinstance(data, str):
            for line in data.split('\n')[:10]:
                self.console.print(f"[{THEME['muted']}]{prefix}[/]{line}")
        else:
            try:
                formatted = json.dumps(data, indent=2, default=str)
                for line in formatted.split('\n')[:15]:
                    self.console.print(f"[{THEME['muted']}]{prefix}[/]{line}")
            except Exception:
                self.console.print(f"[{THEME['muted']}]{prefix}[/]{data}")


dashboard = DashboardManager()
console = dashboard.console


_key_bindings = KeyBindings()
_voice_mode_enabled = {"value": False}


@_key_bindings.add("enter")
def _on_enter(event):
    """Handle Enter key - submit the input."""
    event.current_buffer.validate_and_handle()


@_key_bindings.add("c-j")
def _on_ctrl_j(event):
    """Handle Ctrl+J - insert newline."""
    event.current_buffer.insert_text("\n")


@_key_bindings.add("escape", "enter")
def _on_alt_enter(event):
    """Handle Alt/Option+Enter - insert newline."""
    event.current_buffer.insert_text("\n")


@_key_bindings.add("f5")
def _on_f5(event):
    """Handle F5 - toggle voice input mode."""
    _voice_mode_enabled["value"] = not _voice_mode_enabled["value"]
    mode = "Voice" if _voice_mode_enabled["value"] else "Text"
    print_info(f"Switched to {mode} mode")


_prompt_session = PromptSession(
    history=None,
    multiline=True,
    key_bindings=_key_bindings,
)


def _log_or_print(
    action_type: ActionType,
    message: str,
    *,
    status: str,
    style_key: str,
    symbol: str,
    respect_quiet: bool,
) -> None:
    """Log to dashboard when running, otherwise print to console."""
    if respect_quiet and dashboard.is_quiet:
        return

    if dashboard._is_running:
        dashboard.add_log_entry(action_type, message, status=status)
        return

    console.print(f"  [{THEME[style_key]}]{symbol}[/] {message}")


def print_banner() -> None:
    """Display startup banner."""
    if dashboard.is_quiet:
        return

    console.print()
    console.print(
        f"  [bold {THEME['accent']}]◆[/] [bold {THEME['bright']}]Computer Use Agent[/]"
    )
    console.print(f"    [{THEME['muted']}]Autonomous Desktop & Web Automation[/]")
    console.print()


@contextmanager
def startup_spinner(message: str):
    """Context manager for startup tasks with spinner."""
    if dashboard.is_quiet:
        yield
        return

    status_text = Text()
    status_text.append("  ◌ ", style=f"bold {THEME['accent']}")
    status_text.append(message, style=THEME["muted"])

    spinner = Spinner("dots", text=status_text, style=THEME["accent"])

    try:
        with Live(spinner, console=console, refresh_per_second=10, transient=True):
            yield
    except Exception:
        raise


def print_startup_step(message: str, success: bool = True) -> None:
    """Print a startup step result."""
    if dashboard.is_quiet:
        return

    if success:
        console.print(f"  [{THEME['success']}]✓[/] [{THEME['fg']}]{message}[/]")
    else:
        console.print(f"  [{THEME['error']}]✗[/] [{THEME['fg']}]{message}[/]")


def print_section_header(title: str, icon: str = "") -> None:
    """Print styled section header."""
    if dashboard.is_quiet:
        return

    if dashboard.is_verbose:
        console.print()
        text = Text()
        if icon:
            text.append(f"{icon} ", style=THEME["secondary"])
        text.append(title, style=f"bold {THEME['primary']}")
        console.print(text)
        console.print("─" * 50, style=THEME["border"])


def print_platform_info(capabilities) -> None:
    """Display platform capabilities in compact format."""
    if dashboard.is_quiet:
        return

    if dashboard.is_verbose:
        console.print()
        main_table = Table(
            box=box.ROUNDED,
            show_header=False,
            padding=(0, 1),
            collapse_padding=True,
            border_style=THEME["border"],
        )
        main_table.add_column("", style=f"bold {THEME['muted']}")
        main_table.add_column("", style=THEME["fg"])

        main_table.add_row(
            "Platform",
            f"{capabilities.os_type.title()} {capabilities.os_version}",
        )
        main_table.add_row(
            "Display",
            f"{capabilities.screen_resolution[0]}×{capabilities.screen_resolution[1]} @ {capabilities.scaling_factor}x",
        )

        if capabilities.gpu_available:
            main_table.add_row(
                "GPU", f"[{THEME['success']}]✓ {capabilities.gpu_type}[/]"
            )
        else:
            main_table.add_row("GPU", f"[{THEME['warning']}]CPU mode[/]")

        if capabilities.accessibility_api_available:
            main_table.add_row(
                "Accessibility",
                f"[{THEME['success']}]✓ {capabilities.accessibility_api_type}[/]",
            )
        else:
            main_table.add_row("Accessibility", f"[{THEME['warning']}]Not available[/]")

        panel = Panel(
            Align.left(main_table),
            title=f"[{THEME['primary']}]Platform[/]",
            border_style=THEME["border"],
            padding=(0, 1),
        )
        console.print(panel)
        console.print()
    else:
        platform_str = f"{capabilities.os_type.title()} {capabilities.os_version}"
        display_str = (
            f"{capabilities.screen_resolution[0]}×{capabilities.screen_resolution[1]}"
        )
        gpu_str = (
            f"[{THEME['success']}]GPU[/]"
            if capabilities.gpu_available
            else f"[{THEME['muted']}]CPU[/]"
        )
        acc_str = (
            f"[{THEME['success']}]✓[/]"
            if capabilities.accessibility_api_available
            else f"[{THEME['warning']}]![/]"
        )

        console.print(
            f"  [{THEME['muted']}]Platform[/] [{THEME['fg']}]{platform_str}[/]  "
            f"[{THEME['muted']}]Display[/] [{THEME['fg']}]{display_str}[/]  "
            f"{gpu_str}  [{THEME['muted']}]Accessibility[/] {acc_str}"
        )


def print_status_overview(title: str, items: dict) -> None:
    """Render a concise key-value overview."""
    if dashboard.is_quiet:
        return

    if not items:
        return

    if dashboard.is_verbose:
        table = Table(
            box=box.MINIMAL_DOUBLE_HEAD,
            show_header=False,
            padding=(0, 1),
            collapse_padding=True,
        )
        table.add_column("", style=f"bold {THEME['muted']}")
        table.add_column("", style=THEME["fg"])

        for label, value in items.items():
            table.add_row(label, str(value))

        panel = Panel(
            Align.left(table),
            title=f"[{THEME['primary']}]{title}[/]",
            border_style=THEME["border"],
            padding=(0, 1),
        )
        console.print(panel)
        console.print()
    else:
        parts = []
        for label, value in list(items.items())[:4]:
            parts.append(f"[{THEME['muted']}]{label}[/] [{THEME['fg']}]{value}[/]")
        console.print(f"  {' · '.join(parts)}")


def print_ready() -> None:
    """Print ready message with keyboard hints."""
    if dashboard.is_quiet:
        return

    console.print()
    console.print(
        f"  [{THEME['success']}]●[/] [{THEME['bright']}]Ready[/]  "
        f"[{THEME['muted']}]F5[/] voice  "
        f"[{THEME['muted']}]ESC[/] cancel  "
        f"[{THEME['muted']}]Ctrl+C[/] quit"
    )
    console.print()


def print_verbose_only(message: str) -> None:
    """Print message only in verbose mode."""
    if dashboard.is_verbose:
        console.print(f"  {message}")


def print_step(step: int, action: str, target: str, reasoning: str) -> None:
    """Display agent step with clean formatting."""
    if dashboard.is_verbose:
        text = Text()
        text.append(f"  {step}. ", style=THEME["muted"])
        text.append(action, style=f"bold {THEME['accent']}")
        text.append(" → ", style=THEME["muted"])
        text.append(target, style=THEME["fg"])
        console.print(text)


def print_info(message: str) -> None:
    """Print an info message."""
    _log_or_print(
        ActionType.ANALYZE,
        message,
        status="pending",
        style_key="accent",
        symbol="ℹ",
        respect_quiet=True,
    )


def print_success(message: str) -> None:
    """Print a success message."""
    _log_or_print(
        ActionType.COMPLETE,
        message,
        status="complete",
        style_key="success",
        symbol="✓",
        respect_quiet=True,
    )


def print_warning(message: str) -> None:
    """Print a warning message."""
    _log_or_print(
        ActionType.ERROR,
        message,
        status="pending",
        style_key="warning",
        symbol="⚠",
        respect_quiet=False,
    )


def print_failure(message: str) -> None:
    """Print a failure message."""
    _log_or_print(
        ActionType.ERROR,
        message,
        status="error",
        style_key="error",
        symbol="✗",
        respect_quiet=False,
    )


def print_action_result(success: bool, message: str) -> None:
    """Print the result of an action."""
    if dashboard.is_quiet:
        return

    if success:
        print_success(message)
    else:
        print_failure(message)


@contextmanager
def action_spinner(action: str, target: str = ""):
    """Context manager for actions with status."""
    if dashboard.is_quiet:
        yield
        return

    display = f"{action} {target}".strip()
    idx = dashboard.add_log_entry(ActionType.EXECUTE, display)
    dashboard.set_action(action, target if target else None)

    try:
        yield
        dashboard.update_log_entry(idx, "complete")
    except Exception:
        dashboard.update_log_entry(idx, "error")
        raise
    finally:
        dashboard.clear_action()


def print_task_result(result) -> None:
    """Display the final task result."""
    if dashboard.is_quiet:
        return

    console.print()

    success = (hasattr(result, "overall_success") and result.overall_success) or (
        hasattr(result, "task_completed") and result.task_completed
    )

    if success:
        console.print(f"[bold {THEME['success']}]✓ Complete[/]")
        console.print()

        if hasattr(result, "result") and result.result:
            wrapped = (
                result.result[:200] + "..."
                if len(result.result) > 200
                else result.result
            )
            console.print(f"  [{THEME['fg']}]{wrapped}[/]")

        if hasattr(result, "final_value") and result.final_value:
            console.print(f"  [{THEME['accent']}]Result: {result.final_value}[/]")
    else:
        console.print(f"[bold {THEME['error']}]✗ Failed[/]")

        if hasattr(result, "error") and result.error:
            console.print(f"  [{THEME['error']}]{result.error}[/]")

    console.print()


async def get_task_input(start_with_voice: bool = False) -> Optional[str]:
    """Get task input from user."""
    import asyncio

    try:
        console.print(f"[{THEME['accent']}]What would you like me to do?[/]")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _prompt_session.prompt(
                FormattedText([(THEME["accent"], "❯ ")]),
                multiline=True,
            ),
        )
        return result.strip() if result else None

    except (EOFError, KeyboardInterrupt):
        return None


def format_duration(seconds: float) -> str:
    """Format duration for display."""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"


def explore_tools() -> None:
    """Launch tool explorer for the current session."""
    dashboard.start_tool_explorer()


class HumanAssistanceResult(Enum):
    """Result of human assistance prompt."""

    PROCEED = "proceed"
    RETRY = "retry"
    SKIP = "skip"
    CANCEL = "cancel"


def _resolve_human_choice(choice: str) -> Optional[HumanAssistanceResult]:
    """Map raw input to a HumanAssistanceResult or None if unknown."""
    normalized = choice.strip().lower()

    if normalized in ("", "p", "proceed"):
        return HumanAssistanceResult.PROCEED
    if normalized in ("r", "retry"):
        return HumanAssistanceResult.RETRY
    if normalized in ("s", "skip"):
        return HumanAssistanceResult.SKIP
    if normalized in ("c", "cancel", "q", "quit"):
        return HumanAssistanceResult.CANCEL

    return None


def _log_human_assistance_result(result: HumanAssistanceResult) -> None:
    """Log the outcome of the human assistance prompt."""
    if result is HumanAssistanceResult.PROCEED:
        dashboard.add_log_entry(
            ActionType.COMPLETE,
            "Human assistance: Proceeding",
            status="complete",
        )
    elif result is HumanAssistanceResult.RETRY:
        dashboard.add_log_entry(ActionType.EXECUTE, "Human assistance: Retrying")
    elif result is HumanAssistanceResult.SKIP:
        dashboard.add_log_entry(ActionType.NAVIGATE, "Human assistance: Skipped")
    elif result is HumanAssistanceResult.CANCEL:
        dashboard.add_log_entry(
            ActionType.ERROR, "Human assistance: Cancelled", status="error"
        )


def _finish_human_assistance(result: HumanAssistanceResult) -> HumanAssistanceResult:
    """Hide the panel and log the human assistance outcome."""
    _log_human_assistance_result(result)
    dashboard.hide_human_assistance()
    return result


def prompt_human_assistance(reason: str, instructions: str) -> HumanAssistanceResult:
    """
    Display a styled human assistance dialog integrated in the dashboard.

    Args:
        reason: Why human help is needed
        instructions: What the human needs to do

    Returns:
        HumanAssistanceResult indicating user's choice
    """
    dashboard.show_human_assistance(reason, instructions)
    dashboard._force_refresh()

    if dashboard._use_native_scroll:
        _print_human_assistance_inline(reason, instructions)

    while True:
        try:
            choice = console.input(f"\n  [{THEME['accent']}]Select action ›[/] ")
            resolved = _resolve_human_choice(choice)
            if resolved:
                return _finish_human_assistance(resolved)

        except (EOFError, KeyboardInterrupt):
            return _finish_human_assistance(HumanAssistanceResult.CANCEL)


def _print_human_assistance_inline(reason: str, instructions: str) -> None:
    """Print human assistance panel inline for native scroll mode."""
    console.print()
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")
    console.print(f"[bold {THEME['warning']}]🤝 HUMAN ASSISTANCE REQUIRED[/]")
    console.print()
    if reason:
        console.print(f"[{THEME['muted']}]Reason:[/] {reason}")
    if instructions:
        console.print(f"[{THEME['muted']}]Instructions:[/] {instructions}")
    console.print()
    console.print(
        f"[{THEME['success']}][P][/] Proceed  "
        f"[{THEME['primary']}][R][/] Retry  "
        f"[{THEME['warning']}][S][/] Skip  "
        f"[{THEME['error']}][C][/] Cancel"
    )
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")


class CommandApprovalResult(Enum):
    """Result of command approval prompt."""

    ALLOW_ONCE = "1"
    ALLOW_SESSION = "2"
    DENY = "3"


def _resolve_command_choice(choice: str) -> Optional[CommandApprovalResult]:
    """Map raw input to a CommandApprovalResult or None if unknown."""
    normalized = choice.strip()

    if normalized == "1":
        return CommandApprovalResult.ALLOW_ONCE
    if normalized == "2":
        return CommandApprovalResult.ALLOW_SESSION
    if normalized in ("3", ""):
        return CommandApprovalResult.DENY

    return None


def _log_command_approval_result(result: CommandApprovalResult, command: str) -> None:
    """Log the outcome of the command approval prompt."""
    if result is CommandApprovalResult.ALLOW_ONCE:
        dashboard.add_log_entry(
            ActionType.COMPLETE,
            f"Command approved (once): {command[:40]}...",
            status="complete",
        )
    elif result is CommandApprovalResult.ALLOW_SESSION:
        dashboard.add_log_entry(
            ActionType.COMPLETE,
            f"Command approved (session): {command[:40]}...",
            status="complete",
        )
    elif result is CommandApprovalResult.DENY:
        dashboard.add_log_entry(
            ActionType.ERROR,
            "Command denied by user",
            status="error",
        )


def _finish_command_approval(result: CommandApprovalResult, command: str) -> str:
    """Hide the panel and log the command approval outcome."""
    _log_command_approval_result(result, command)
    dashboard.hide_command_approval()
    return result.value


def print_command_approval(command: str) -> str:
    """
    Display command approval dialog integrated in the dashboard.

    Args:
        command: The shell command requiring approval

    Returns:
        User choice: "1" (allow once), "2" (allow session), "3" (deny)
    """
    dashboard.show_command_approval(command)

    while True:
        try:
            choice = console.input(f"\n  [{THEME['accent']}]Select (1/2/3) ›[/] ")
            resolved = _resolve_command_choice(choice)
            if resolved:
                return _finish_command_approval(resolved, command)
            console.print(f"  [{THEME['warning']}]Invalid choice. Enter 1, 2, or 3.[/]")

        except (EOFError, KeyboardInterrupt):
            return _finish_command_approval(CommandApprovalResult.DENY, command)
