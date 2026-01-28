"""
Windows-specific accessibility implementation.

This package contains all Windows-specific code including:
- Role normalization (mapping Edit→TextField, etc.)
- pywinauto integration
- Native click handling
"""

from .accessibility import WindowsAccessibility
from .role_normalizer import normalize_windows_role, normalize_windows_element

__all__ = [
    "WindowsAccessibility",
    "normalize_windows_role",
    "normalize_windows_element",
]
