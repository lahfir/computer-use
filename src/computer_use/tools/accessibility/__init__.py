"""
Tier 1: Platform accessibility API tools for maximum accuracy.

This package provides cross-platform accessibility APIs with a unified interface.
Platform-specific implementations are in their respective subdirectories:
- macos/ - atomacos-based implementation
- windows/ - pywinauto-based implementation
- linux/ - pyatspi-based implementation

The shared modules (protocol.py, element_registry.py, cache_manager.py) are
platform-agnostic and contain ZERO platform-specific code.
"""

import platform
from typing import Optional

from .cache_manager import AccessibilityCacheManager
from .element_registry import (
    ElementRecord,
    VersionedElementRegistry,
    compute_element_id,
    shorten_role,
)
from .linux import LinuxAccessibility
from .macos import MacOSAccessibility
from .protocol import AccessibilityProtocol
from .windows import WindowsAccessibility


def get_accessibility_tool(
    screen_width: int = 0, screen_height: int = 0
) -> Optional[AccessibilityProtocol]:
    """
    Factory function to get the appropriate accessibility tool for the current platform.

    Args:
        screen_width: Screen width (0 = auto-detect)
        screen_height: Screen height (0 = auto-detect)

    Returns:
        Platform-specific accessibility tool implementing AccessibilityProtocol,
        or None if the platform is not supported.
    """
    system = platform.system().lower()

    if system == "darwin":
        return MacOSAccessibility(screen_width, screen_height)

    elif system == "windows":
        width = screen_width if screen_width > 0 else 1920
        height = screen_height if screen_height > 0 else 1080
        return WindowsAccessibility(width, height)

    elif system == "linux":
        width = screen_width if screen_width > 0 else 1920
        height = screen_height if screen_height > 0 else 1080
        return LinuxAccessibility(width, height)

    return None


__all__ = [
    "get_accessibility_tool",
    "AccessibilityProtocol",
    "MacOSAccessibility",
    "WindowsAccessibility",
    "LinuxAccessibility",
    "VersionedElementRegistry",
    "ElementRecord",
    "AccessibilityCacheManager",
    "shorten_role",
    "compute_element_id",
]
