"""
Tier 1: Platform accessibility API tools for maximum accuracy.
"""

from .macos_accessibility import MacOSAccessibility
from .windows_accessibility import WindowsAccessibility
from .linux_accessibility import LinuxAccessibility

__all__ = [
    "MacOSAccessibility",
    "WindowsAccessibility",
    "LinuxAccessibility",
]
