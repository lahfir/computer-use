"""
Cross-platform input control for mouse and keyboard.
"""

from typing import List, Optional
import pyautogui
import time


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


class InputTool:
    """
    Safe mouse and keyboard input control with validation.
    """

    def __init__(self, validator=None):
        """
        Initialize input tool with optional coordinate validator.

        Args:
            validator: CoordinateValidator instance
        """
        self.validator = validator

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        validate: bool = True,
    ) -> bool:
        """
        Click at specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            button: Mouse button (left, right, middle)
            clicks: Number of clicks (1 for single, 2 for double)
            validate: Whether to validate coordinates first

        Returns:
            True if click was executed
        """
        if validate and self.validator:
            is_valid, error = self.validator.validate_coordinates(x, y)
            if not is_valid:
                raise ValueError(f"Invalid coordinates: {error}")

            if not self.validator.rate_limit_check():
                time.sleep(0.1)

        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return True

    def double_click(self, x: int, y: int, validate: bool = True) -> bool:
        """
        Double-click at specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            validate: Whether to validate coordinates first

        Returns:
            True if double-click was executed
        """
        return self.click(x, y, clicks=2, validate=validate)

    def right_click(self, x: int, y: int, validate: bool = True) -> bool:
        """
        Right-click at specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            validate: Whether to validate coordinates first

        Returns:
            True if right-click was executed
        """
        return self.click(x, y, button="right", validate=validate)

    def move_to(self, x: int, y: int, duration: float = 0.2) -> bool:
        """
        Move mouse cursor to specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Time in seconds for movement

        Returns:
            True if movement was executed
        """
        pyautogui.moveTo(x, y, duration=duration)
        return True

    def drag(
        self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5
    ) -> bool:
        """
        Drag from start to end coordinates.

        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Ending X coordinate
            end_y: Ending Y coordinate
            duration: Time in seconds for drag

        Returns:
            True if drag was executed
        """
        self.move_to(start_x, start_y, duration=0.1)
        pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)
        return True

    def type_text(self, text: str, interval: float = 0.05) -> bool:
        """
        Type text with specified interval between keystrokes.

        Args:
            text: Text to type
            interval: Delay between keystrokes in seconds

        Returns:
            True if typing completed
        """
        pyautogui.write(text, interval=interval)
        return True

    def press_key(self, key: str) -> bool:
        """
        Press a single key.

        Args:
            key: Key name (enter, escape, tab, etc.)

        Returns:
            True if key press executed
        """
        pyautogui.press(key)
        return True

    def hotkey(self, *keys: str) -> bool:
        """
        Press a keyboard shortcut (combination of keys).

        Args:
            keys: Keys to press together (e.g., 'ctrl', 'c')

        Returns:
            True if hotkey executed
        """
        pyautogui.hotkey(*keys)
        return True

    def scroll(
        self, clicks: int, x: Optional[int] = None, y: Optional[int] = None
    ) -> bool:
        """
        Scroll vertically.

        Args:
            clicks: Number of scroll clicks (positive=up, negative=down)
            x: Optional X coordinate for scroll position
            y: Optional Y coordinate for scroll position

        Returns:
            True if scroll executed
        """
        if x is not None and y is not None:
            self.move_to(x, y, duration=0.1)

        pyautogui.scroll(clicks)
        return True
