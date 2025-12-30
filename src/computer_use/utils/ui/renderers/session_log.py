"""
Session log renderer: final summary output.
"""

from typing import Optional
from rich.console import RenderableType, Group
from rich.text import Text
from rich.panel import Panel
from rich import box

from .base import BaseRenderer
from ..state import TaskState
from ..theme import THEME, ICONS


class SessionLogRenderer(BaseRenderer):
    """Renders the complete session log/summary."""

    def render(self, state: TaskState) -> Optional[RenderableType]:
        """Render the complete session summary."""
        sections = []

        # Header
        sections.append(self._render_header(state))
        sections.append(Text())

        # Agent summaries
        for agent_id, agent in state.agents.items():
            sections.append(self._render_agent_summary(agent))
            sections.append(Text())

        # Result panel (if complete)
        if state.status in ("complete", "error"):
            sections.append(self._render_result(state))
            sections.append(Text())

        # Stats footer
        sections.append(self._render_stats(state))

        return Group(*sections)

    def _render_header(self, state: TaskState) -> RenderableType:
        """Render the session header."""
        status_icon = ICONS["success"] if state.status == "complete" else ICONS["error"]
        status_text = "COMPLETE" if state.status == "complete" else "FAILED"
        status_style = (
            THEME["tool_success"] if state.status == "complete" else THEME["error"]
        )

        header = Text()
        header.append("═" * 70, style=THEME["border"])
        header.append("\n")
        header.append("  TASK: ", style=THEME["muted"])
        header.append(state.description[:60], style=f"bold {THEME['text']}")
        if len(state.description) > 60:
            header.append("...", style=THEME["muted"])
        header.append(f"  {status_icon} {status_text}", style=status_style)
        header.append("\n")
        header.append("═" * 70, style=THEME["border"])

        return header

    def _render_agent_summary(self, agent) -> Panel:
        """Render summary for a single agent."""
        lines = []

        # Tool summary table
        if agent.tools:
            for tool in agent.tools:
                line = Text()

                # Status icon
                if tool.status == "success":
                    line.append(f"  {ICONS['success']} ", style=THEME["tool_success"])
                elif tool.status == "error":
                    line.append(f"  {ICONS['error']} ", style=THEME["tool_error"])
                else:
                    line.append("  ○ ", style=THEME["muted"])

                # Tool name and duration
                line.append(tool.name, style=THEME["text"])
                if tool.duration > 0:
                    duration_str = (
                        f"{tool.duration:.1f}s"
                        if tool.duration < 60
                        else f"{int(tool.duration // 60)}m"
                    )
                    spacing = " " * max(1, 40 - len(tool.name))
                    line.append(f"{spacing}{duration_str}", style=THEME["muted"])

                lines.append(line)
        else:
            lines.append(Text("  No tools executed", style=THEME["muted"]))

        # Agent title
        title = Text()
        title.append(f" {agent.name} ", style=f"bold {THEME['text']}")

        return Panel(
            Group(*lines),
            title=title,
            title_align="left",
            border_style=THEME["border"],
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_result(self, state: TaskState) -> Panel:
        """Render the final result."""
        content = Text()

        if state.status == "complete":
            content.append("Task completed successfully.", style=THEME["tool_success"])
        else:
            content.append("Task failed.", style=THEME["error"])

        return Panel(
            content,
            title=f"[{THEME['text']}]RESULT[/]",
            title_align="left",
            border_style=THEME["border"],
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_stats(self, state: TaskState) -> Text:
        """Render the stats footer."""
        line = Text()
        line.append("═" * 70, style=THEME["border"])
        line.append("\n")
        line.append("  ", style=THEME["text"])

        # Duration
        duration = state.duration
        if duration < 60:
            duration_str = f"{int(duration)}s"
        else:
            mins = int(duration // 60)
            secs = int(duration % 60)
            duration_str = f"{mins}m {secs}s"
        line.append(f"Duration: {duration_str}", style=THEME["text"])

        line.append(f" {ICONS['separator']} ", style=THEME["muted"])

        # Tools
        success = state.total_tools - state.failed_tools
        line.append(f"Tools: {success}/{state.total_tools}", style=THEME["text"])
        if state.failed_tools > 0:
            line.append(f" ({state.failed_tools} failed)", style=THEME["error"])

        line.append(f" {ICONS['separator']} ", style=THEME["muted"])

        # Tokens
        line.append(
            f"Tokens: {state.token_input}→{state.token_output}", style=THEME["text"]
        )

        line.append(f" {ICONS['separator']} ", style=THEME["muted"])

        # Agents
        line.append(f"Agents: {len(state.agents)}", style=THEME["text"])

        line.append("\n")
        line.append("═" * 70, style=THEME["border"])

        return line
