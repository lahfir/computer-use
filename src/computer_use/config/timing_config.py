"""
Timing and retry configuration for GUI automation.

All timing values are in seconds unless otherwise specified.
These values can be adjusted based on system performance and platform.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TimingConfig:
    """
    Centralized timing configuration for GUI automation.

    Prevents hardcoded values scattered throughout the codebase.
    """

    # UI State Change Delays
    ui_state_change_delay: float = 0.2
    """Time to wait after clicking for UI to update"""

    app_launch_base_delay: float = 0.3
    """Base delay after launching an app"""

    app_focus_delay: float = 0.5
    """Delay when bringing app to front"""

    accessibility_api_delay: float = 0.1
    """Delay for accessibility API to settle"""

    typing_delay: float = 0.3
    """Delay before typing to ensure field is focused"""

    # Retry Configuration
    app_launch_max_attempts: int = 5
    """Max attempts to verify app launched"""

    app_launch_frontmost_attempts: int = 3
    """Max attempts to verify app is frontmost"""

    app_launch_retry_interval: float = 0.2
    """Seconds between app launch verification attempts"""

    accessibility_retry_count: int = 3
    """Number of retries for accessibility API queries"""

    # Timeouts
    applescript_timeout: int = 2
    """Timeout for AppleScript commands (seconds)"""

    shell_command_timeout: int = 30
    """Default timeout for shell commands (seconds)"""

    verification_code_timeout: int = 60
    """Timeout for SMS verification code retrieval"""

    verification_code_poll_interval: float = 1.0
    """Polling interval for verification codes"""

    # Drag Operation
    drag_duration: float = 0.5
    """Duration of drag operations"""

    # Window Dimensions (Fallbacks)
    default_window_height: int = 1000
    """Fallback window height if bounds detection fails"""

    default_window_width: int = 800
    """Fallback window width if bounds detection fails"""


# Global instance
DEFAULT_TIMING = TimingConfig()


def get_timing_config() -> TimingConfig:
    """
    Get the timing configuration instance.

    Can be extended to load from environment variables or config file.
    """
    return DEFAULT_TIMING


def create_custom_timing(
    ui_delay: Optional[float] = None,
    max_attempts: Optional[int] = None,
    retry_interval: Optional[float] = None,
) -> TimingConfig:
    """
    Create a custom timing configuration.

    Args:
        ui_delay: Override UI state change delay
        max_attempts: Override max launch attempts
        retry_interval: Override retry interval

    Returns:
        TimingConfig with custom values
    """
    config = TimingConfig()

    if ui_delay is not None:
        config.ui_state_change_delay = ui_delay
    if max_attempts is not None:
        config.app_launch_max_attempts = max_attempts
    if retry_interval is not None:
        config.app_launch_retry_interval = retry_interval

    return config
