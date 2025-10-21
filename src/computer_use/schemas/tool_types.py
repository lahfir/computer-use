"""
Type definitions for tools and their return values.
"""

from typing import TypedDict, Optional, Any, Tuple, Protocol, List
from PIL import Image


class ClickResult(TypedDict, total=False):
    """
    Result from click/double-click/right-click operations.
    """

    success: bool
    method: str
    coordinates: Optional[Tuple[int, int]]
    matched_text: Optional[str]
    confidence: Optional[float]
    error: Optional[str]


class TypeResult(TypedDict, total=False):
    """
    Result from type text operations.
    """

    success: bool
    method: str
    typed_text: Optional[str]
    error: Optional[str]


class ScrollResult(TypedDict, total=False):
    """
    Result from scroll operations.
    """

    success: bool
    method: str
    data: Optional[dict]
    error: Optional[str]


class ReadResult(TypedDict, total=False):
    """
    Result from read screen operations.
    """

    success: bool
    method: str
    data: Optional[dict]
    error: Optional[str]


class OpenAppResult(TypedDict, total=False):
    """
    Result from opening application.
    """

    success: bool
    method: str
    error: Optional[str]


class ActionExecutionResult(TypedDict, total=False):
    """
    Generic result from action execution.
    """

    success: bool
    method: str
    coordinates: Optional[Tuple[int, int]]
    matched_text: Optional[str]
    confidence: Optional[float]
    data: Optional[dict]
    error: Optional[str]
    typed_text: Optional[str]


class CapabilitiesSummary(TypedDict):
    """
    Summary of platform capabilities and available tools.
    """

    os_type: str
    os_version: str
    accessibility_api: Optional[str]
    screen_resolution: Tuple[int, int]
    gpu_available: bool
    gpu_type: Optional[str]
    available_tools: List[str]
    tier1_available: bool
    tier2_available: bool
    tier3_available: bool


class Tool(Protocol):
    """
    Base protocol for all tools.
    """

    pass


class ScreenshotTool(Protocol):
    """
    Screenshot capture tool protocol.
    """

    scaling_factor: float

    def capture(self) -> Image.Image:
        """
        Capture current screen.

        Returns:
            PIL Image of screen
        """
        ...


class InputTool(Protocol):
    """
    Input automation tool protocol.
    """

    def click(self, x: int, y: int, validate: bool = False) -> bool:
        """
        Click at coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            validate: Whether to validate coordinates

        Returns:
            True if successful
        """
        ...

    def double_click(self, x: int, y: int, validate: bool = False) -> bool:
        """
        Double-click at coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            validate: Whether to validate coordinates

        Returns:
            True if successful
        """
        ...

    def right_click(self, x: int, y: int, validate: bool = False) -> bool:
        """
        Right-click at coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
            validate: Whether to validate coordinates

        Returns:
            True if successful
        """
        ...

    def type_text(self, text: str) -> None:
        """
        Type text at current cursor position.

        Args:
            text: Text to type
        """
        ...

    def scroll(self, amount: int) -> None:
        """
        Scroll by amount.

        Args:
            amount: Positive for up, negative for down
        """
        ...


class ProcessTool(Protocol):
    """
    Process management tool protocol.
    """

    def open_application(self, app_name: str) -> dict:
        """
        Open application by name.

        Args:
            app_name: Application name

        Returns:
            Dictionary with success status
        """
        ...


class AccessibilityTool(Protocol):
    """
    Accessibility API tool protocol.
    """

    available: bool

    def find_elements(self, label: str, app_name: Optional[str] = None) -> List[dict]:
        """
        Find elements by label.

        Args:
            label: Element label to search for
            app_name: Optional app name to search within

        Returns:
            List of element dictionaries
        """
        ...

    def get_all_interactive_elements(self, app_name: str) -> List[dict]:
        """
        Get all interactive elements in app.

        Args:
            app_name: Application name

        Returns:
            List of element dictionaries
        """
        ...

    def get_app_window_bounds(
        self, app_name: str
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Get application window bounds.

        Args:
            app_name: Application name

        Returns:
            Bounds as (x, y, width, height) or None
        """
        ...

    def click_element(
        self, target: str, app_name: Optional[str] = None
    ) -> Tuple[bool, Any]:
        """
        Click element by target.

        Args:
            target: Target element identifier
            app_name: Optional app name

        Returns:
            Tuple of (clicked, element)
        """
        ...


class OCRToolProtocol(Protocol):
    """
    OCR tool protocol.
    """

    def find_text(
        self,
        screenshot: Image.Image,
        target_text: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        fuzzy: bool = True,
    ) -> List[Any]:
        """
        Find text in screenshot.

        Args:
            screenshot: PIL Image to search
            target_text: Text to find
            region: Optional region to search
            fuzzy: Whether to allow partial matches

        Returns:
            List of OCRResult objects
        """
        ...

    def extract_all_text(self, screenshot: Image.Image) -> List[Any]:
        """
        Extract all text from screenshot.

        Args:
            screenshot: PIL Image to analyze

        Returns:
            List of OCRResult objects
        """
        ...
