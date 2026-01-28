"""
Linux-specific accessibility implementation.

This package contains all Linux-specific code including:
- Role normalization (converting AT-SPI lowercase roles to PascalCase)
- pyatspi integration
- Native click handling via doAction
"""

from .accessibility import LinuxAccessibility
from .role_normalizer import normalize_linux_role, normalize_linux_element

__all__ = [
    "LinuxAccessibility",
    "normalize_linux_role",
    "normalize_linux_element",
]
