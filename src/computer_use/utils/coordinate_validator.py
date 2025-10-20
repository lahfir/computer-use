"""
Coordinate validation and safety checks for GUI automation.
"""

from typing import Tuple, Optional
import time


class CoordinateValidator:
    """
    Validates coordinates before executing GUI actions.
    """

    def __init__(self, screen_width: int, screen_height: int):
        """
        Initialize validator with screen dimensions.

        Args:
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.last_action_time = 0
        self.min_action_interval = 0.1

    def is_within_bounds(self, x: int, y: int) -> bool:
        """
        Check if coordinates are within screen bounds.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if coordinates are valid
        """
        return 0 <= x < self.screen_width and 0 <= y < self.screen_height

    def is_safe_region(self, x: int, y: int) -> bool:
        """
        Check if coordinates are in a safe region (not system UI).

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if region is safe to click
        """
        if y < 30:
            return False

        edge_margin = 5
        if (
            x < edge_margin
            or x > self.screen_width - edge_margin
            or y < edge_margin
            or y > self.screen_height - edge_margin
        ):
            return False

        return True

    def validate_coordinates(
        self, x: int, y: int, strict: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate coordinates before action execution.

        Args:
            x: X coordinate
            y: Y coordinate
            strict: Whether to apply strict safety checks

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.is_within_bounds(x, y):
            return (False, f"Coordinates ({x}, {y}) are outside screen bounds")

        if strict and not self.is_safe_region(x, y):
            return (False, f"Coordinates ({x}, {y}) are in a protected region")

        return (True, None)

    def rate_limit_check(self) -> bool:
        """
        Check if enough time has passed since last action.

        Returns:
            True if action is allowed
        """
        current_time = time.time()
        if current_time - self.last_action_time < self.min_action_interval:
            return False

        self.last_action_time = current_time
        return True

    def validate_bounds(
        self, x: int, y: int, width: int, height: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate element bounds are reasonable.

        Args:
            x: X coordinate
            y: Y coordinate
            width: Element width
            height: Element height

        Returns:
            Tuple of (is_valid, error_message)
        """
        if width <= 0 or height <= 0:
            return (False, "Invalid element dimensions")

        if width > self.screen_width or height > self.screen_height:
            return (False, "Element bounds exceed screen size")

        if not self.is_within_bounds(x, y):
            return (False, "Element position outside screen")

        if not self.is_within_bounds(x + width, y + height):
            return (False, "Element extends outside screen")

        return (True, None)
