"""
Agent renderer: displays agent status blocks with visual hierarchy.
"""

from typing import Optional, List
from rich.console import RenderableType, Group
from rich.panel import Panel
from rich.text import Text
from rich import box

from .base import BaseRenderer
from ..state import TaskState, AgentState
from ..theme import THEME, ICONS


class AgentRenderer(BaseRenderer):
    """Renders agent status blocks with tools and thinking."""

    def render(self, state: TaskState) -> Optional[RenderableType]:
        """Render all agents as panels."""
        if not state.agents:
            return None

        panels = []
        for agent_id in state.agents:
            agent = state.agents[agent_id]
            panel = self._render_agent_panel(agent, agent_id == state.active_agent_id)
            panels.append(panel)

        return Group(*panels)

    def _render_agent_panel(self, agent: AgentState, is_active: bool) -> Panel:
        """Render a single agent as a panel."""
        # Header with status badge
        status_text, status_style = self._get_status_display(agent, is_active)
        title = Text()
        title.append(f" {agent.name} ", style=f"bold {THEME['header']}")
        title.append(f" {status_text} ", style=status_style)

        # Build panel content
        content = self._build_agent_content(agent, is_active)

        border_style = THEME["agent_active"] if is_active else THEME["border"]

        return Panel(
            content,
            title=title,
            title_align="left",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _get_status_display(
        self, agent: AgentState, is_active: bool
    ) -> tuple[str, str]:
        """Get status text and style for agent."""
        status_map = {
            "idle": (f"{ICONS['agent_idle']} IDLE", THEME["muted"]),
            "thinking": (f"{ICONS['agent_active']} THINKING", THEME["thinking"]),
            "executing": (f"{ICONS['agent_active']} EXECUTING", THEME["agent_active"]),
            "complete": (f"{ICONS['success']} COMPLETE", THEME["tool_success"]),
            "error": (f"{ICONS['error']} ERROR", THEME["tool_error"]),
        }

        if is_active and agent.status in ("idle", "thinking"):
            return (f"{ICONS['agent_active']} ACTIVE", f"bold {THEME['agent_active']}")

        return status_map.get(agent.status, ("", THEME["muted"]))

    def _build_agent_content(
        self, agent: AgentState, is_active: bool
    ) -> RenderableType:
        """Build the content inside an agent panel."""
        lines: List[RenderableType] = []

        # Current thought if active
        if is_active and agent.current_thought:
            thought_text = Text()
            thought_text.append(f"  {ICONS['thinking']} ", style=THEME["thinking"])
            thought_text.append(
                agent.current_thought[:150], style=f"italic {THEME['thinking']}"
            )
            if len(agent.current_thought) > 150:
                thought_text.append("...", style=f"italic {THEME['muted']}")
            lines.append(thought_text)
            lines.append(Text())

        # Tools summary
        if agent.tools:
            from .tool import ToolRenderer

            tool_renderer = ToolRenderer(self.console, self.verbosity)
            for tool in agent.tools:
                tool_display = tool_renderer.render_tool(tool)
                lines.append(tool_display)

        if not lines:
            if is_active:
                lines.append(
                    Text("  Waiting for action...", style=f"italic {THEME['muted']}")
                )
            else:
                lines.append(Text("  No activity", style=THEME["muted"]))

        return Group(*lines)

    def render_compact(self, agent: AgentState, is_active: bool) -> Text:
        """Render a compact single-line agent summary."""
        line = Text()

        icon = ICONS["agent_active"] if is_active else ICONS["agent_idle"]
        name_style = f"bold {THEME['agent_active']}" if is_active else THEME["muted"]

        line.append(f"{icon} ", style=name_style)
        line.append(agent.name, style=name_style)

        if agent.tools:
            success = sum(1 for t in agent.tools if t.status == "success")
            total = len(agent.tools)
            line.append(f" [{success}/{total}]", style=THEME["muted"])

        return line
