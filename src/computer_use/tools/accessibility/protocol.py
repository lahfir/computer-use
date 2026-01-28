"""
Platform-agnostic protocol definition for cross-platform accessibility APIs.

All platform implementations (macOS, Windows, Linux) must implement this protocol
to ensure consistent behavior across platforms. This file contains ZERO
platform-specific code - no AX, UIA, AT-SPI references allowed.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple


class AccessibilityProtocol(ABC):
    """
    Unified accessibility API contract for all platforms.

    This is an abstract base class that defines the interface all platform
    implementations must follow. It uses ONLY platform-agnostic concepts.
    """

    available: bool

    @abstractmethod
    def get_elements(
        self, app_name: str, interactive_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get UI elements from an application.

        Args:
            app_name: Application name to get elements from
            interactive_only: If True, only return interactive elements

        Returns:
            List of element dictionaries with standardized keys:
            - element_id: Stable semantic ID (deterministic, not random)
            - role: Element type (Button, TextField, MenuItem, etc.)
            - label: Human-readable label
            - identifier: Platform-specific unique ID
            - center: [x, y] coordinates
            - bounds: [x, y, width, height]
            - has_actions: Whether element is clickable
            - enabled: Whether element is enabled
            - focused: Whether element has focus
            - app_name: Application name
        """
        ...

    @abstractmethod
    def click_by_id(
        self, element_id: str, click_type: str = "single"
    ) -> Tuple[bool, str]:
        """
        Click element by its stable ID.

        Args:
            element_id: Element ID from get_elements()
            click_type: Click type - single, double, or right

        Returns:
            Tuple of (success, message) describing the result.
            If element is stale, message should indicate refresh needed.
            If element not found, message should indicate it.
        """
        ...

    @abstractmethod
    def invalidate_cache(self, app_name: Optional[str] = None) -> None:
        """
        Invalidate element cache after interactions.

        Args:
            app_name: If provided, only invalidate for this app
        """
        ...

    @abstractmethod
    def get_frontmost_app(self) -> Optional[str]:
        """Get the name of the frontmost application."""
        ...

    @abstractmethod
    def is_app_frontmost(self, app_name: str) -> bool:
        """Check if the specified app is frontmost."""
        ...

    @abstractmethod
    def get_window_bounds(self, app_name: str) -> Optional[Tuple[int, int, int, int]]:
        """
        Get bounds of the app's main window.

        Returns:
            Tuple of (x, y, width, height) or None if not found
        """
        ...

    @abstractmethod
    def get_running_apps(self) -> List[str]:
        """Get names of all running applications."""
        ...

    @abstractmethod
    def get_app(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        """
        Get application reference by name.

        Args:
            app_name: Application name (case-insensitive partial match)
            retry_count: Number of retry attempts

        Returns:
            App reference or None
        """
        ...

    @abstractmethod
    def get_windows(self, app: Any) -> List[Any]:
        """
        Get windows for an application.

        Args:
            app: Application reference

        Returns:
            List of window references
        """
        ...

    @abstractmethod
    def is_app_running(self, app_name: str) -> bool:
        """Check if an application is running."""
        ...

    def set_active_app(self, app_name: str) -> None:
        """
        Set and cache the active application.

        Default implementation invalidates cache and gets app.
        Subclasses may override for platform-specific behavior.
        """
        self.invalidate_cache(app_name)
        self.get_app(app_name)

    def get_running_app_names(self) -> List[str]:
        """Backward compatible alias for get_running_apps."""
        return self.get_running_apps()

    def get_frontmost_app_name(self) -> Optional[str]:
        """Backward compatible alias for get_frontmost_app."""
        return self.get_frontmost_app()

    def get_app_window_bounds(
        self, app_name: Optional[str] = None
    ) -> Optional[Tuple[int, int, int, int]]:
        """Backward compatible alias for get_window_bounds."""
        if not app_name:
            return None
        return self.get_window_bounds(app_name)

    def clear_cache(self) -> None:
        """Clear all caches. Default calls invalidate_cache(None)."""
        self.invalidate_cache(None)

    def clear_app_cache(self) -> None:
        """Backward compatible alias for clear_cache."""
        self.clear_cache()
