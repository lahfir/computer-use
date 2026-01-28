"""
macOS-specific accessibility implementation.

This package contains all macOS-specific code including:
- Role normalization (stripping AX prefix)
- atomacos integration
- Native click handling
"""

from .accessibility import MacOSAccessibility
from .role_normalizer import normalize_macos_role, normalize_macos_element

__all__ = [
    "MacOSAccessibility",
    "normalize_macos_role",
    "normalize_macos_element",
]
