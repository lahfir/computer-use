"""
Prompts module: task input and human assistance dialogs.
Uses InquirerPy for interactive arrow-key selection menus.
"""

import asyncio
import logging
from contextlib import contextmanager
from enum import Enum
from typing import List, Optional

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.utils import InquirerPyStyle
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.status import Status

from .theme import THEME, ICONS
from .state import VerbosityLevel, ActionType

logger = logging.getLogger(__name__)


INQUIRER_STYLE = InquirerPyStyle(
    {
        "questionmark": "#e5c07b",
        "answermark": "#98c379",
        "answer": "#61afef",
        "input": "#abb2bf",
        "question": "#abb2bf",
        "answered_question": "#636d83",
        "instruction": "#636d83",
        "long_instruction": "#636d83",
        "pointer": "#c678dd bold",
        "checkbox": "#98c379",
        "separator": "#636d83",
        "skipped": "#636d83",
        "validator": "#e06c75",
        "marker": "#e5c07b",
        "fuzzy_prompt": "#c678dd",
        "fuzzy_info": "#636d83",
        "fuzzy_border": "#4b5263",
        "fuzzy_match": "#c678dd",
        "spinner_pattern": "#c678dd",
        "spinner_text": "#abb2bf",
    }
)


# Key bindings for prompt
_key_bindings = KeyBindings()
_voice_mode_enabled = {"value": False}

# Task history for quick re-selection (max 10 recent tasks)
_task_history: List[str] = []
_MAX_TASK_HISTORY = 10


def add_to_task_history(task: str) -> None:
    """
    Add a task to the history for quick re-selection.

    Args:
        task: The task description to add
    """
    global _task_history
    task = task.strip()
    if not task:
        return

    if task in _task_history:
        _task_history.remove(task)

    _task_history.insert(0, task)

    if len(_task_history) > _MAX_TASK_HISTORY:
        _task_history = _task_history[:_MAX_TASK_HISTORY]


def get_task_history() -> List[str]:
    """Get the current task history."""
    return _task_history.copy()


def select_from_task_history(console: Console) -> Optional[str]:
    """
    Show interactive task history selection with arrow keys.

    Returns:
        Selected task or None if cancelled/new task requested
    """
    if not _task_history:
        console.print(f"  [{THEME['muted']}]No task history yet.[/]")
        return None

    console.print()

    choices = [
        Choice(value=task, name=task[:60] + "..." if len(task) > 60 else task)
        for task in _task_history
    ]
    choices.append(Choice(value=None, name="[Type new task...]"))

    try:
        selected = inquirer.select(
            message="Select recent task (or type new)",
            choices=choices,
            pointer="›",
            style=INQUIRER_STYLE,
            qmark="",
            amark="✓",
        ).execute()

        return selected

    except (EOFError, KeyboardInterrupt):
        return None


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
    """Context manager for startup tasks with animated spinner using fresh console."""
    from rich.console import Console as FreshConsole

    fresh_console = FreshConsole(force_terminal=True)
    status = Status(
        f"    {message}",
        spinner="dots",
        spinner_style=THEME["tool_pending"],
        console=fresh_console,
        refresh_per_second=20,
    )
    status.start()
    try:
        yield
    finally:
        status.stop()


async def get_voice_input(console: Console) -> Optional[str]:
    """
    Capture voice input using the VoiceInputService.

    Returns:
        Transcribed text or None if voice input failed or was cancelled
    """
    try:
        from computer_use.services.voice_input_service import VoiceInputService
        from computer_use.services.audio_capture import AudioCapture
    except ImportError as e:
        logger.error(f"Voice input dependencies not available: {e}")
        console.print(
            f"  [{THEME['error']}]Voice input unavailable: missing dependencies[/]"
        )
        return None

    if not VoiceInputService.check_api_key_configured():
        console.print(f"  [{THEME['warning']}]Voice input requires DEEPGRAM_API_KEY[/]")
        return None

    if not AudioCapture.check_microphone_available():
        console.print(f"  [{THEME['warning']}]No microphone available[/]")
        return None

    try:
        service = VoiceInputService()
    except ValueError as e:
        console.print(f"  [{THEME['error']}]Voice service error: {e}[/]")
        return None

    interim_text = {"value": ""}
    status_line = {"ref": None}

    def on_interim(text: str):
        """Update the interim transcription display."""
        interim_text["value"] = text
        if status_line["ref"]:
            status_line["ref"].update(
                f"    [{THEME['muted']}]🎤[/] [{THEME['text']}]{text}[/]"
            )

    console.print(
        f"  [{THEME['tool_pending']}]🎤 Listening... (press Enter to stop)[/]"
    )

    status = Status(
        f"    [{THEME['muted']}]Waiting for speech...[/]",
        spinner="dots",
        spinner_style=THEME["tool_pending"],
        console=console,
    )
    status_line["ref"] = status
    status.start()

    success = await service.start_transcription(interim_callback=on_interim)

    if not success:
        status.stop()
        error = service.get_error()
        console.print(f"  [{THEME['error']}]Failed to start voice input: {error}[/]")
        return None

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def wait_for_enter():
        """Wait for Enter key in a thread."""
        try:
            input()
            loop.call_soon_threadsafe(stop_event.set)
        except (EOFError, KeyboardInterrupt):
            loop.call_soon_threadsafe(stop_event.set)

    loop.run_in_executor(None, wait_for_enter)

    await stop_event.wait()

    status.stop()
    result = await service.stop_transcription()

    if result:
        console.print(f"  [{THEME['tool_success']}]✓[/] [{THEME['text']}]{result}[/]")
    else:
        console.print(f"  [{THEME['muted']}]No speech detected[/]")

    return result if result else None


async def get_task_input(
    console: Console, start_with_voice: bool = False
) -> Optional[str]:
    """
    Get task input from user via text or voice.

    Args:
        console: Rich console for output
        start_with_voice: If True, start with voice input mode

    Returns:
        User input text or None if cancelled
    """
    use_voice = start_with_voice or _voice_mode_enabled["value"]

    if use_voice:
        console.print(f"[{THEME['text']}]What would you like me to do?[/]")
        result = await get_voice_input(console)
        if result:
            _voice_mode_enabled["value"] = False
            return result
        console.print(f"  [{THEME['muted']}]Falling back to text input...[/]")

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
    """
    Display a human assistance dialog with arrow-key selection menu.

    Uses InquirerPy for interactive navigation instead of text input.
    """
    console.print()
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")
    console.print(f"[bold {THEME['warning']}]🤝 HUMAN ASSISTANCE REQUIRED[/]")
    console.print()

    if reason:
        console.print(f"[{THEME['muted']}]Reason:[/] {reason}")
    if instructions:
        console.print(f"[{THEME['muted']}]Instructions:[/] {instructions}")

    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")
    console.print()

    try:
        choice = inquirer.select(
            message="Select action",
            choices=[
                Choice(value="proceed", name="Proceed - Continue with the task"),
                Choice(value="retry", name="Retry - Try again with different approach"),
                Choice(value="skip", name="Skip - Skip this step"),
                Choice(value="cancel", name="Cancel - Stop the entire task"),
            ],
            default="proceed",
            pointer="›",
            style=INQUIRER_STYLE,
            qmark="",
            amark="✓",
        ).execute()

        result_map = {
            "proceed": HumanAssistanceResult.PROCEED,
            "retry": HumanAssistanceResult.RETRY,
            "skip": HumanAssistanceResult.SKIP,
            "cancel": HumanAssistanceResult.CANCEL,
        }
        return result_map.get(choice, HumanAssistanceResult.CANCEL)

    except (EOFError, KeyboardInterrupt):
        return HumanAssistanceResult.CANCEL


def print_command_approval(console: Console, command: str) -> str:
    """
    Display command approval dialog with arrow-key selection menu.

    Uses InquirerPy for interactive navigation instead of text input.
    """
    console.print()
    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")
    console.print(f"[bold {THEME['warning']}]⚠ COMMAND REQUIRES APPROVAL[/]")
    console.print()

    console.print(f"[{THEME['muted']}]Command:[/]")
    console.print(f"  [{THEME['warning']}]{command}[/]")

    console.print(f"[bold {THEME['warning']}]{'─' * 50}[/]")
    console.print()

    try:
        choice = inquirer.select(
            message="Select action",
            choices=[
                Choice(value="1", name="Allow once"),
                Choice(value="2", name="Allow for session"),
                Choice(value="3", name="Deny & stop"),
            ],
            default="1",
            pointer="›",
            style=INQUIRER_STYLE,
            qmark="",
            amark="✓",
        ).execute()

        return choice or CommandApprovalResult.DENY.value

    except (EOFError, KeyboardInterrupt):
        return CommandApprovalResult.DENY.value


def print_task_result(console: Console, result) -> None:
    """Display the final task result with nice formatting."""
    from rich.markdown import Markdown
    from rich.padding import Padding

    console.print()

    success = (hasattr(result, "overall_success") and result.overall_success) or (
        hasattr(result, "task_completed") and result.task_completed
    )

    if success:
        console.print(f"[bold {THEME['tool_success']}]{ICONS['success']} Complete[/]")
        console.print()

        if hasattr(result, "result") and result.result:
            md = Markdown(result.result)
            console.print(Padding(md, (0, 2)))

        if hasattr(result, "final_value") and result.final_value:
            console.print()
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
