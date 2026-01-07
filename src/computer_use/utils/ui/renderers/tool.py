"""
Tool renderer: displays tool calls with inputs/outputs.
"""

from typing import Optional
from rich.console import RenderableType, Group
from rich.text import Text
from rich.spinner import Spinner

from .base import BaseRenderer
from ..state import TaskState, ToolState
from ..theme import THEME, ICONS
from ..formatters import format_dict_inline


class ToolRenderer(BaseRenderer):
    """Renders tool execution with inputs, outputs, and status."""

    def render(self, state: TaskState) -> Optional[RenderableType]:
        """Render all tools from all agents."""
        tools = []
        for agent in state.agents.values():
            for tool in agent.tools:
                tools.append(self.render_tool(tool))
        return Group(*tools) if tools else None

    def render_tool(self, tool: ToolState) -> RenderableType:
        """Render a single tool execution block."""
        lines = []

        # Header line: [status] tool_name                          duration
        header = self._render_tool_header(tool)
        lines.append(header)

        # Input line
        if tool.input_data:
            input_line = self._render_input(tool.input_data)
            lines.append(input_line)

        # Output or error line
        if tool.status == "success" and tool.output_data:
            output_line = self._render_output(tool.output_data)
            lines.append(output_line)
        elif tool.status == "error" and tool.error:
            error_line = self._render_error(tool.error)
            lines.append(error_line)
        elif tool.status == "pending":
            # Show spinner for pending tools
            spinner_line = Text("      ")
            spinner_line.append_text(
                Text("Processing...", style=f"italic {THEME['muted']}")
            )
            lines.append(spinner_line)

        return Group(*lines)

    def _render_tool_header(self, tool: ToolState) -> Text:
        """
        Render the tool header with status icon and inline duration.

        Format: ⟳ tool_name (5.00s)
        """
        line = Text()

        if tool.status == "pending":
            line.append(f"  {ICONS['pending']} ", style=f"bold {THEME['tool_pending']}")
        elif tool.status == "success":
            line.append(f"  {ICONS['success']} ", style=f"bold {THEME['tool_success']}")
        elif tool.status == "error":
            line.append(f"  {ICONS['error']} ", style=f"bold {THEME['tool_error']}")
        else:
            line.append("  ○ ", style=THEME["muted"])

        name_style = THEME["tool_error"] if tool.status == "error" else THEME["text"]
        line.append(tool.name, style=f"bold {name_style}")

        if tool.duration > 0:
            duration_str = self._format_duration(tool.duration)
            line.append(f" ({duration_str})", style=THEME["muted"])

        return line

    def _render_input(self, input_data: dict) -> Text:
        """Render tool input parameters - full display, no truncation."""
        line = Text()
        line.append(f"      {ICONS['input']} ", style=THEME["input"])

        cleaned_data = self._clean_input_data(input_data)
        line.append(format_dict_inline(cleaned_data), style=THEME["text"])
        return line

    def _clean_input_data(self, input_data: dict) -> dict:
        """
        Clean up input data for display.
        Extracts actual values from JSON arrays/objects if malformed.
        """
        import json

        cleaned = {}
        for key, value in input_data.items():
            if isinstance(value, str) and (
                value.strip().startswith("[") or value.strip().startswith("{")
            ):
                try:
                    parsed = json.loads(value.strip())
                    if isinstance(parsed, list) and len(parsed) > 0:
                        first = parsed[0]
                        if isinstance(first, dict) and "command" in first:
                            cleaned[key] = first["command"]
                            continue
                    elif isinstance(parsed, dict) and "command" in parsed:
                        cleaned[key] = parsed["command"]
                        continue
                except json.JSONDecodeError:
                    pass
            cleaned[key] = value
        return cleaned

    def _render_output(self, output_data) -> Text:
        """
        Render tool output as clean indented block.

        Formats long outputs with proper line breaks and indentation.
        """
        line = Text()
        line.append(f"      {ICONS['output']} ", style=THEME["output"])

        if isinstance(output_data, str):
            formatted = self._format_output_string(output_data)
            line.append(formatted, style=THEME["text"])
        elif isinstance(output_data, dict):
            formatted = self._format_output_dict(output_data)
            line.append(formatted, style=THEME["text"])
        else:
            line.append(str(output_data), style=THEME["text"])

        return line

    def _format_output_string(self, output: str) -> str:
        """
        Format string output with proper line breaks and indentation.

        Handles multi-line outputs by indenting continuation lines.
        """
        if not output:
            return "success"

        output = output.strip()
        lines = [line for line in output.split("\n") if line.strip()]

        if not lines:
            return "success"

        if len(lines) == 1 and len(lines[0]) <= 80:
            return lines[0]

        if len(lines) == 1:
            return lines[0][:77] + "..."

        indent = "\n          │ "
        formatted = lines[0]

        for line in lines[1:15]:
            formatted += f"{indent}{line.strip()}"

        if len(lines) > 15:
            formatted += f"{indent}... ({len(lines) - 15} more lines)"

        return formatted

    def _format_output_dict(self, output: dict) -> str:
        """
        Format dictionary output as clean key-value pairs.

        Groups and summarizes complex nested data.
        """
        if not output:
            return "success"

        parts = []
        indent = "         "

        for key, value in list(output.items())[:5]:
            if isinstance(value, list):
                parts.append(f"{key}: {len(value)} items")
            elif isinstance(value, dict):
                parts.append(f"{key}: {{...}}")
            elif isinstance(value, str) and len(str(value)) > 50:
                parts.append(f"{key}: {str(value)[:47]}...")
            else:
                parts.append(f"{key}: {value}")

        if len(output) > 5:
            parts.append(f"... +{len(output) - 5} more")

        if len(parts) == 1:
            return parts[0]

        result = parts[0]
        for part in parts[1:]:
            result += f"\n{indent}{part}"

        return result

    def _render_error(self, error: str) -> Text:
        """Render tool error - full display."""
        line = Text()
        line.append(f"      {ICONS['error']} ", style=f"bold {THEME['error']}")
        line.append(error, style=THEME["error"])
        return line

    def _format_duration(self, seconds: float) -> str:
        """Format duration for display."""
        if seconds < 0.01:
            return "<0.01s"
        elif seconds < 1:
            return f"{seconds:.2f}s"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        else:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"

    def render_tool_with_spinner(self, tool: ToolState) -> RenderableType:
        """Render a pending tool with an animated spinner."""
        if tool.status != "pending":
            return self.render_tool(tool)

        spinner = Spinner("dots", text=f" {tool.name}", style=THEME["tool_pending"])
        lines = [
            Text("  ").append_text(Text.from_markup(f"[{THEME['tool_pending']}]")),
            spinner,
        ]

        if tool.input_data:
            lines.append(self._render_input(tool.input_data))

        return Group(*lines)
