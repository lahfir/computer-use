"""
Prompts module: task input and human assistance dialogs.
"""

import asyncio
from contextlib import contextmanager
from enum import Enum
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from .theme import THEME, ICONS
from .state import VerbosityLevel, ActionType


# Key bindings for prompt
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


_prompt_session = PromptSession(
    history=None,
    multiline=True,
    key_bindings=_key_bindings,
)


class HumanAssistanceResult(Enum):
    """Result of human assistance prompt."""

    PROCEED = "proceed"
    RETRY = "retry"
    SKIP = "skip"
    CANCEL = "cancel"


class CommandApprovalResult(Enum):
    """Result of command approval prompt."""

    ALLOW_ONCE = "1"
    ALLOW_SESSION = "2"
    DENY = "3"


def print_banner(
    console: Console, verbosity: VerbosityLevel = VerbosityLevel.NORMAL
) -> None:
    """Display startup banner with professional styling."""
    if verbosity == VerbosityLevel.QUIET:
        return

    console.print()
    console.print(f"  [{THEME['border']}]╭{'─' * 52}╮[/]")
    console.print(
        f"  [{THEME['border']}]│[/]  [bold {THEME['agent_active']}]◆[/] "
        f"[bold {THEME['text']}]Computer Use Agent[/]"
        f"{' ' * 26}[{THEME['border']}]│[/]"
    )
    console.print(
        f"  [{THEME['border']}]│[/]    "
        f"[{THEME['muted']}]Autonomous Desktop & Web Automation[/]"
        f"{' ' * 8}[{THEME['border']}]│[/]"
    )
    console.print(f"  [{THEME['border']}]╰{'─' * 52}╯[/]")
    console.print()


def print_startup_step(console: Console, message: str, success: bool = True) -> None:
    """Print a startup step result with clear visual feedback."""
    icon = ICONS["success"] if success else ICONS["error"]
    style = THEME["tool_success"] if success else THEME["error"]
    console.print(f"    [{style}]{icon}[/] [{THEME['text']}]{message}[/]")


def print_platform_info(
    console: Console, capabilities, verbosity: VerbosityLevel = VerbosityLevel.NORMAL
) -> None:
    """Display platform capabilities in a clean inline format."""
    if verbosity == VerbosityLevel.QUIET:
        return

    platform_str = f"{capabilities.os_type.title()} {capabilities.os_version}"
    display_str = (
        f"{capabilities.screen_resolution[0]}×{capabilities.screen_resolution[1]}"
    )
    gpu_icon = ICONS["success"] if capabilities.gpu_available else "○"
    gpu_style = THEME["tool_success"] if capabilities.gpu_available else THEME["muted"]
    acc_icon = ICONS["success"] if capabilities.accessibility_api_available else "✗"
    acc_style = (
        THEME["tool_success"]
        if capabilities.accessibility_api_available
        else THEME["warning"]
    )

    console.print()
    console.print(
        f"    [{THEME['muted']}]Platform[/] [{THEME['text']}]{platform_str}[/]  │  "
        f"[{THEME['muted']}]Display[/] [{THEME['text']}]{display_str}[/]  │  "
        f"[{gpu_style}]{gpu_icon}[/] [{THEME['muted']}]GPU[/]  │  "
        f"[{acc_style}]{acc_icon}[/] [{THEME['muted']}]Accessibility[/]"
    )


def print_status_overview(console: Console, title: str, items: dict) -> None:
    """Render a concise status overview with tool and service info."""
    if not items:
        return

    console.print()
    parts = []
    for label, value in list(items.items())[:4]:
        icon = "⚙" if label == "Tools" else "◉" if label == "Webhook" else "◆"
        parts.append(
            f"[{THEME['tool_pending']}]{icon}[/] "
            f"[{THEME['muted']}]{label}[/] [{THEME['text']}]{value}[/]"
        )
    console.print(f"    {' │ '.join(parts)}")


def print_ready(console: Console) -> None:
    """Print ready message with keyboard hints in a clean format."""
    console.print()
    console.print(f"    [{THEME['border']}]{'─' * 48}[/]")
    console.print(
        f"    [{THEME['tool_success']}]{ICONS['agent_active']}[/] "
        f"[bold {THEME['text']}]Ready[/]  "
        f"[{THEME['muted']}]│[/]  "
        f"[{THEME['muted']}]F5[/] [{THEME['text']}]voice[/]  "
        f"[{THEME['muted']}]ESC[/] [{THEME['text']}]cancel[/]  "
        f"[{THEME['muted']}]Ctrl+C[/] [{THEME['text']}]quit[/]"
    )
    console.print()


@contextmanager
def startup_spinner(console: Console, message: str):
    """Context manager for startup tasks with animated spinner."""
    from rich.text import Text

    spinner_text = Text()
    spinner_text.append("    ")
    spinner_text.append(message, style=THEME["text"])

    spinner = Spinner("dots", text=spinner_text, style=THEME["tool_pending"])

    try:
        with Live(spinner, console=console, refresh_per_second=12, transient=True):
            yield
    except Exception:
        raise


async def get_task_input(
    console: Console, start_with_voice: bool = False
) -> Optional[str]:
    """Get task input from user."""
    try:
        console.print(f"[{THEME['text']}]What would you like me to do?[/]")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _prompt_session.prompt(
                FormattedText([(THEME["text"], "❯ ")]),
                multiline=True,
            ),
        )
        return result.strip() if result else None

    except (EOFError, KeyboardInterrupt):
        return None


def prompt_human_assistance(
    console: Console, reason: str, instructions: str
) -> HumanAssistanceResult:
    """Display a human assistance dialog."""
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
        f"[{THEME['tool_success']}][P][/] Proceed  "
        f"[{THEME['text']}][R][/] Retry  "
        f"[{THEME['warning']}][S][/] Skip  "
        f"[{THEME['error']}][C][/] Cancel"
    )
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")

    while True:
        try:
            choice = (
                console.input(f"\n  [{THEME['text']}]Select action ›[/] ")
                .strip()
                .lower()
            )

            if choice in ("", "p", "proceed"):
                return HumanAssistanceResult.PROCEED
            if choice in ("r", "retry"):
                return HumanAssistanceResult.RETRY
            if choice in ("s", "skip"):
                return HumanAssistanceResult.SKIP
            if choice in ("c", "cancel", "q", "quit"):
                return HumanAssistanceResult.CANCEL

        except (EOFError, KeyboardInterrupt):
            return HumanAssistanceResult.CANCEL


def print_command_approval(console: Console, command: str) -> str:
    """Display command approval dialog."""
    console.print()
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")
    console.print(f"[bold {THEME['warning']}]⚠ COMMAND REQUIRES APPROVAL[/]")
    console.print()

    cmd_display = command[:80] + "..." if len(command) > 80 else command
    console.print(f"[{THEME['muted']}]Command:[/] [{THEME['warning']}]{cmd_display}[/]")

    console.print()
    console.print(
        f"[{THEME['tool_success']}][1][/] Allow once  "
        f"[{THEME['text']}][2][/] Allow for session  "
        f"[{THEME['error']}][3][/] Deny & stop"
    )
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")

    while True:
        try:
            choice = console.input(f"\n  [{THEME['text']}]Select (1/2/3) ›[/] ").strip()

            if choice == "1":
                return CommandApprovalResult.ALLOW_ONCE.value
            if choice == "2":
                return CommandApprovalResult.ALLOW_SESSION.value
            if choice in ("3", ""):
                return CommandApprovalResult.DENY.value

            console.print(f"  [{THEME['warning']}]Invalid choice. Enter 1, 2, or 3.[/]")

        except (EOFError, KeyboardInterrupt):
            return CommandApprovalResult.DENY.value


def print_task_result(console: Console, result) -> None:
    """Display the final task result."""
    console.print()

    success = (hasattr(result, "overall_success") and result.overall_success) or (
        hasattr(result, "task_completed") and result.task_completed
    )

    if success:
        console.print(f"[bold {THEME['tool_success']}]{ICONS['success']} Complete[/]")
        console.print()

        if hasattr(result, "result") and result.result:
            wrapped = (
                result.result[:200] + "..."
                if len(result.result) > 200
                else result.result
            )
            console.print(f"  [{THEME['text']}]{wrapped}[/]")

        if hasattr(result, "final_value") and result.final_value:
            console.print(f"  [{THEME['text']}]Result: {result.final_value}[/]")
    else:
        console.print(f"[bold {THEME['error']}]{ICONS['error']} Failed[/]")

        if hasattr(result, "error") and result.error:
            console.print(f"  [{THEME['error']}]{result.error}[/]")

    console.print()


# Helper functions for common operations


@contextmanager
def action_spinner_ctx(console: Console, action: str, target: str = ""):
    """Context manager for actions with status."""
    from .dashboard import dashboard

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


def print_action_result_fn(console: Console, success: bool, message: str) -> None:
    """Print the result of an action."""
    from .dashboard import dashboard

    if dashboard.is_quiet:
        return

    if success:
        console.print(f"  [{THEME['tool_success']}]{ICONS['success']}[/] {message}")
    else:
        console.print(f"  [{THEME['error']}]{ICONS['error']}[/] {message}")


def print_verbose_only_fn(console: Console, message: str) -> None:
    """Print message only in verbose mode."""
    from .dashboard import dashboard

    if dashboard.is_verbose:
        console.print(f"  {message}")


def print_info(console: Console, message: str) -> None:
    """Print an info message."""
    console.print(f"  [{THEME['text']}]ℹ[/] {message}")


def print_success(console: Console, message: str) -> None:
    """Print a success message."""
    console.print(f"  [{THEME['tool_success']}]{ICONS['success']}[/] {message}")


def print_warning(console: Console, message: str) -> None:
    """Print a warning message."""
    console.print(f"  [{THEME['warning']}]{ICONS['warning']}[/] {message}")


def print_failure(console: Console, message: str) -> None:
    """Print a failure message."""
    console.print(f"  [{THEME['error']}]{ICONS['error']}[/] {message}")


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
