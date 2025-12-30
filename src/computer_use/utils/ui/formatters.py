"""
Data formatting utilities for the UI.
"""

import json
from typing import Any, Dict
from rich.text import Text
from rich.syntax import Syntax
from .theme import THEME


def format_key_value(key: str, value: Any, max_len: int = 60) -> str:
    """Format a key-value pair for display."""
    val_str = str(value)
    if len(val_str) > max_len:
        val_str = val_str[: max_len - 3] + "..."

    if isinstance(value, str):
        val_str = f'"{val_str}"'

    return f"{key}={val_str}"


def format_dict_inline(data: Dict[str, Any], max_items: int = 3) -> str:
    """Format a dictionary as an inline string."""
    if not data:
        return ""

    items = []
    for i, (k, v) in enumerate(data.items()):
        if i >= max_items:
            items.append(f"+{len(data) - max_items} more")
            break
        items.append(format_key_value(k, v))

    return ", ".join(items)


def format_json_block(data: Any) -> Syntax:
    """Format data as a syntax-highlighted JSON block."""
    try:
        if isinstance(data, str):
            # Try to parse if it looks like JSON
            if data.strip().startswith("{") or data.strip().startswith("["):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    pass

        json_str = json.dumps(data, indent=2, default=str)
        return Syntax(
            json_str, "json", theme="monokai", background_color=THEME["panel_bg"]
        )
    except Exception:
        return Text(str(data))


def truncate_text(text: str, max_lines: int = 5, max_width: int = 100) -> str:
    """Truncate long text blocks."""
    lines = text.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines.append(f"... (+{len(lines) - max_lines} lines)")

    truncated_lines = []
    for line in lines:
        if len(line) > max_width:
            truncated_lines.append(line[:max_width] + "...")
        else:
            truncated_lines.append(line)

    return "\n".join(truncated_lines)
