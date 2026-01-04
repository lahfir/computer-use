"""
Enterprise-grade terminal UI package.

This package provides a modular, high-performance UI system for the
Computer Use Agent with clear visual hierarchy and rich feedback.
"""

from contextlib import contextmanager

from .state import (
    VerbosityLevel,
    ActionType,
    ToolState,
    AgentState,
    TaskState,
)

from .theme import THEME, ICONS

from .dashboard import (
    DashboardManager,
    LogBatcher,
    dashboard,
    console,
)

from .prompts import (
    HumanAssistanceResult,
    CommandApprovalResult,
    format_duration,
)

from .prompts import (
    print_banner as _print_banner,
    print_startup_step as _print_startup_step,
    print_platform_info as _print_platform_info,
    print_status_overview as _print_status_overview,
    print_ready as _print_ready,
    startup_spinner as _startup_spinner,
    get_task_input as _get_task_input,
    get_voice_input as _get_voice_input,
    prompt_human_assistance as _prompt_human_assistance,
    print_command_approval as _print_command_approval,
    print_task_result as _print_task_result,
    print_info as _print_info,
    print_success as _print_success,
    print_warning as _print_warning,
    print_failure as _print_failure,
    print_verbose_only_fn as _print_verbose_only_fn,
    add_to_task_history as _add_to_task_history,
    get_task_history as _get_task_history,
    select_from_task_history as _select_from_task_history,
)

from .formatters import (
    format_dict_inline,
    format_json_block,
    truncate_text,
)

from .animations import (
    tool_spinner,
    thinking_spinner,
    action_status,
    create_spinner,
    create_task_progress,
    create_tool_progress,
    AnimatedStatus,
)


def print_banner():
    """Display startup banner using singleton console."""
    _print_banner(console, dashboard.verbosity)


def print_startup_step(message: str, success: bool = True):
    """Print a startup step result using singleton console."""
    _print_startup_step(console, message, success)


def print_platform_info(capabilities):
    """Display platform capabilities using singleton console."""
    _print_platform_info(console, capabilities, dashboard.verbosity)


def print_status_overview(title: str, items: dict):
    """Render a concise key-value overview using singleton console."""
    _print_status_overview(console, title, items)


def print_ready():
    """Print ready message using singleton console."""
    _print_ready(console)


def startup_spinner(message: str):
    """Context manager for startup tasks with spinner."""
    return _startup_spinner(console, message)


async def get_task_input(start_with_voice: bool = False):
    """Get task input from user using singleton console."""
    return await _get_task_input(console, start_with_voice)


async def get_voice_input():
    """Get voice input from user using singleton console."""
    return await _get_voice_input(console)


def prompt_human_assistance(reason: str, instructions: str) -> HumanAssistanceResult:
    """Display a human assistance dialog using singleton console."""
    return _prompt_human_assistance(console, reason, instructions)


def print_command_approval(command: str) -> str:
    """Display command approval dialog using singleton console."""
    return _print_command_approval(console, command)


def print_task_result(result):
    """Display the final task result using singleton console."""
    _print_task_result(console, result)


def print_info(message: str):
    """Print an info message using singleton console."""
    _print_info(console, message)


def print_success(message: str):
    """Print a success message using singleton console."""
    _print_success(console, message)


def print_warning(message: str):
    """Print a warning message using singleton console."""
    _print_warning(console, message)


def print_failure(message: str):
    """Print a failure message using singleton console."""
    _print_failure(console, message)


@contextmanager
def action_spinner(action: str, target: str = ""):
    """
    No-op context manager.

    Tool status is now handled by the dashboard through step_callback.
    This avoids duplicate logging.
    """
    yield


def print_action_result(success: bool, message: str):
    """
    No-op function.

    Tool results are now handled by the dashboard through log_tool_complete.
    This avoids duplicate logging.
    """
    pass


def print_verbose_only(message: str):
    """Print message only in verbose mode using singleton console."""
    _print_verbose_only_fn(console, message)


def add_to_task_history(task: str):
    """Add a task to the history for quick re-selection."""
    _add_to_task_history(task)


def get_task_history():
    """Get the current task history."""
    return _get_task_history()


def select_from_task_history():
    """Show interactive task history selection with arrow keys."""
    return _select_from_task_history(console)


__all__ = [
    # State management
    "VerbosityLevel",
    "ActionType",
    "ToolState",
    "AgentState",
    "TaskState",
    # Theme
    "THEME",
    "ICONS",
    # Dashboard
    "DashboardManager",
    "LogBatcher",
    "dashboard",
    "console",
    # Prompts (backward-compatible wrappers)
    "HumanAssistanceResult",
    "CommandApprovalResult",
    "print_banner",
    "print_startup_step",
    "print_platform_info",
    "print_status_overview",
    "print_ready",
    "startup_spinner",
    "get_task_input",
    "get_voice_input",
    "prompt_human_assistance",
    "print_command_approval",
    "print_task_result",
    "print_info",
    "print_success",
    "print_warning",
    "print_failure",
    "action_spinner",
    "print_action_result",
    "print_verbose_only",
    "format_duration",
    "add_to_task_history",
    "get_task_history",
    "select_from_task_history",
    # Formatters
    "format_dict_inline",
    "format_json_block",
    "truncate_text",
    # Animations
    "tool_spinner",
    "thinking_spinner",
    "action_status",
    "create_spinner",
    "create_task_progress",
    "create_tool_progress",
    "AnimatedStatus",
]
