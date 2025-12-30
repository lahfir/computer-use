"""
Status bar renderer: sticky footer with metrics.
"""

from typing import Optional
from rich.console import RenderableType
from rich.text import Text

from .base import BaseRenderer
from ..state import TaskState
from ..theme import THEME, ICONS


class StatusBarRenderer(BaseRenderer):
    """Renders the status bar with current metrics."""

    def render(self, state: TaskState) -> Optional[RenderableType]:
        """Render the status bar."""
        return self._build_status_line(state)

    def _build_status_line(self, state: TaskState) -> Text:
        """Build the status bar text."""
        line = Text()

        # Active agent
        if state.active_agent_id:
            agent = state.agents.get(state.active_agent_id)
            if agent:
                line.append(f" {ICONS['agent_active']} ", style=THEME["agent_active"])
                line.append(agent.name, style=f"bold {THEME['text']}")
                line.append(f" {ICONS['separator']} ", style=THEME["muted"])

                # Agent status
                status_style = self._get_status_style(agent.status)
                line.append(agent.status.upper(), style=status_style)
        else:
            line.append(f" {ICONS['agent_idle']} ", style=THEME["muted"])
            line.append("Ready", style=THEME["muted"])

        line.append(f" {ICONS['separator']} ", style=THEME["muted"])

        # Duration
        duration_str = self._format_duration(state.duration)
        line.append("⏱ ", style=THEME["muted"])
        line.append(duration_str, style=THEME["text"])

        line.append(f" {ICONS['separator']} ", style=THEME["muted"])

        # Tool stats
        success = state.total_tools - state.failed_tools
        line.append("Tools: ", style=THEME["muted"])
        if state.failed_tools > 0:
            line.append(f"{success}", style=THEME["tool_success"])
            line.append(f"/{state.total_tools} ", style=THEME["text"])
            line.append(f"({state.failed_tools}{ICONS['error']})", style=THEME["error"])
        else:
            line.append(f"{success}/{state.total_tools}", style=THEME["text"])

        line.append(f" {ICONS['separator']} ", style=THEME["muted"])

        # Token usage
        total_tokens = state.token_input + state.token_output
        if total_tokens > 0:
            token_str = self._format_tokens(total_tokens)
            line.append("◇ ", style=THEME["muted"])
            line.append(token_str, style=THEME["text"])

        return line

    def _get_status_style(self, status: str) -> str:
        """Get style for status text."""
        styles = {
            "idle": THEME["muted"],
            "thinking": f"bold {THEME['thinking']}",
            "executing": f"bold {THEME['agent_active']}",
            "complete": f"bold {THEME['tool_success']}",
            "error": f"bold {THEME['error']}",
        }
        return styles.get(status, THEME["muted"])

    def _format_duration(self, seconds: float) -> str:
        """Format duration for display."""
        if seconds < 60:
            return f"{int(seconds)}s"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"

    def _format_tokens(self, tokens: int) -> str:
        """Format token count."""
        if tokens >= 1000:
            return f"{tokens / 1000:.1f}k"
        return str(tokens)

    def render_inline(self, state: TaskState) -> str:
        """Render as a plain string for terminal status line."""
        parts = []

        # Agent
        if state.active_agent_id:
            agent = state.agents.get(state.active_agent_id)
            if agent:
                parts.append(f"{agent.name} | {agent.status}")
        else:
            parts.append("Ready")

        # Duration
        parts.append(f"⏱ {self._format_duration(state.duration)}")

        # Tools
        success = state.total_tools - state.failed_tools
        parts.append(f"Tools: {success}/{state.total_tools}")

        # Tokens
        total_tokens = state.token_input + state.token_output
        if total_tokens > 0:
            parts.append(f"◇ {self._format_tokens(total_tokens)}")

        return " │ ".join(parts)
