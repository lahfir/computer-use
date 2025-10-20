"""
Platform detection system to identify OS capabilities and available APIs.
"""

import platform
import sys
from typing import Tuple, List, Optional, Literal
from pydantic import BaseModel, Field


class PlatformCapabilities(BaseModel):
    """
    Detected platform capabilities and available APIs.
    """

    os_type: Literal["macos", "windows", "linux"] = Field(
        description="Detected operating system type"
    )
    os_version: str = Field(description="Operating system version string")
    accessibility_api_available: bool = Field(
        description="Whether platform accessibility API is available"
    )
    accessibility_api_type: Optional[str] = Field(
        default=None,
        description="Type of accessibility API (NSAccessibility, UIA, AT-SPI)",
    )
    screen_resolution: Tuple[int, int] = Field(
        description="Screen resolution as (width, height)"
    )
    scaling_factor: float = Field(description="Display scaling factor", default=1.0)
    supported_tools: List[str] = Field(
        description="List of available automation tools", default_factory=list
    )


def detect_platform() -> PlatformCapabilities:
    """
    Detect current platform and test API availability.

    Returns:
        PlatformCapabilities with detected system information
    """
    system = platform.system().lower()

    if system == "darwin":
        os_type = "macos"
    elif system == "windows":
        os_type = "windows"
    elif system == "linux":
        os_type = "linux"
    else:
        os_type = "linux"

    os_version = platform.release()

    accessibility_api_available = False
    accessibility_api_type = None
    supported_tools = []

    if os_type == "macos":
        accessibility_api_available = _test_macos_accessibility()
        if accessibility_api_available:
            accessibility_api_type = "NSAccessibility"
            supported_tools.append("macos_accessibility")
    elif os_type == "windows":
        accessibility_api_available = _test_windows_accessibility()
        if accessibility_api_available:
            accessibility_api_type = "UI Automation"
            supported_tools.append("windows_accessibility")
    elif os_type == "linux":
        accessibility_api_available = _test_linux_accessibility()
        if accessibility_api_available:
            accessibility_api_type = "AT-SPI"
            supported_tools.append("linux_accessibility")

    supported_tools.extend(["screenshot", "input", "process", "file", "ocr", "cv"])

    screen_resolution = _get_screen_resolution()
    scaling_factor = _get_scaling_factor()

    return PlatformCapabilities(
        os_type=os_type,
        os_version=os_version,
        accessibility_api_available=accessibility_api_available,
        accessibility_api_type=accessibility_api_type,
        screen_resolution=screen_resolution,
        scaling_factor=scaling_factor,
        supported_tools=supported_tools,
    )


def _test_macos_accessibility() -> bool:
    """
    Test if macOS accessibility APIs are available.
    """
    try:
        import AppKit
        import Quartz

        return True
    except ImportError:
        return False


def _test_windows_accessibility() -> bool:
    """
    Test if Windows UI Automation is available.
    """
    try:
        import pywinauto

        return True
    except ImportError:
        return False


def _test_linux_accessibility() -> bool:
    """
    Test if Linux AT-SPI is available.
    """
    try:
        import pyatspi

        return True
    except ImportError:
        return False


def _get_screen_resolution() -> Tuple[int, int]:
    """
    Get primary screen resolution.
    """
    try:
        import pyautogui

        size = pyautogui.size()
        return (size.width, size.height)
    except Exception:
        return (1920, 1080)


def _get_scaling_factor() -> float:
    """
    Get display scaling factor.
    """
    system = platform.system().lower()

    if system == "darwin":
        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen:
                return float(screen.backingScaleFactor())
        except Exception:
            pass
    elif system == "windows":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            return user32.GetDpiForSystem() / 96.0
        except Exception:
            pass

    return 1.0
