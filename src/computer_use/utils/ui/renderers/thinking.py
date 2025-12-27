"""
Thinking renderer: displays agent reasoning/thoughts.
"""

from typing import Optional
from rich.console import RenderableType
from rich.text import Text
from rich.panel import Panel
from rich import box

from .base import BaseRenderer
from ..state import TaskState
from ..theme import THEME, ICONS


class ThinkingRenderer(BaseRenderer):
    """Renders agent thinking/reasoning blocks."""

    def render(self, state: TaskState) -> Optional[RenderableType]:
        """Render current thinking from active agent."""
        if not state.active_agent_id:
            return None

        agent = state.agents.get(state.active_agent_id)
        if not agent or not agent.current_thought:
            return None

        return self.render_thought(agent.current_thought)

    def render_thought(self, thought: str, max_width: int = 80) -> RenderableType:
        """
        Render a thinking block with distinctive styling.

        Format:
          ┊ Thinking ────────────────────────────────────────────────────────┊
          │ The agent's reasoning text goes here, wrapped nicely...         │
          └─────────────────────────────────────────────────────────────────┘
        """
        # Wrap long thoughts
        wrapped = self._wrap_text(thought, max_width - 6)

        content = Text()
        for i, line in enumerate(wrapped.split("\n")):
            if i > 0:
                content.append("\n")
            content.append(f"  {line}", style=f"italic {THEME['thinking']}")

        return Panel(
            content,
            title=f"[{THEME['thinking']}]{ICONS['thinking']} Thinking[/]",
            title_align="left",
            border_style=THEME["thinking"],
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def render_inline(self, thought: str) -> Text:
        """Render full inline thought (no truncation for full reasoning)."""
        line = Text()
        line.append(f"  {ICONS['thinking']} ", style=THEME["thinking"])
        line.append(thought, style=f"italic {THEME['thinking']}")
        return line

    def _wrap_text(self, text: str, width: int) -> str:
        """Simple text wrapping."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) + 1 <= width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)

        if current_line:
            lines.append(" ".join(current_line))

        return "\n".join(lines)
