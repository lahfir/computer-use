"""
Cross-platform screenshot capture tool.
"""

import base64
import io
from typing import Optional, Tuple, Dict, Any
from PIL import Image
import pyautogui
import platform


class ScreenshotTool:
    """
    Cross-platform screenshot capture with region support.
    Handles Retina/HiDPI display scaling automatically.
    """

    def __init__(self):
        """
        Initialize and detect display scaling.
        """
        self.scaling_factor = self._detect_scaling()
        self.os_type = platform.system().lower()
        self.active_window_bounds = None  # Store active window bounds

    def _detect_scaling(self) -> float:
        """
        Detect display scaling factor (Retina = 2.0, normal = 1.0).
        """
        screen_size = pyautogui.size()
        test_screenshot = pyautogui.screenshot()

        # If screenshot is larger than screen, we have scaling
        if test_screenshot.width > screen_size.width:
            scaling = test_screenshot.width / screen_size.width
            return scaling
        return 1.0

    def capture_active_window(
        self, app_name: Optional[str] = None
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Capture ONLY the active window, not entire screen.

        Args:
            app_name: Optional app name to ensure correct window

        Returns:
            (PIL Image of window, dict with bounds and metadata)
        """
        try:
            if self.os_type == "darwin":
                return self._capture_active_window_macos(app_name)
            elif self.os_type == "windows":
                return self._capture_active_window_windows(app_name)
            else:
                return self._capture_active_window_linux(app_name)
        except Exception as e:
            print(f"  ⚠️  Window capture error: {e}, using full screen")
            return self.capture(), {
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0,
                "type": "fullscreen",
            }

    def _capture_active_window_macos(
        self, app_name: Optional[str] = None
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """Capture active window on macOS using Quartz."""
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
        )

        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )

        target_window = None
        for window in window_list:
            owner_name = window.get("kCGWindowOwnerName", "")
            layer = window.get("kCGWindowLayer", 999)

            if layer == 0:
                if app_name:
                    if app_name.lower() in owner_name.lower():
                        target_window = window
                        break
                else:
                    target_window = window
                    break

        if not target_window:
            print("  ⚠️  Window not found, using full screen")
            return self.capture(), {
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0,
                "type": "fullscreen",
            }

        bounds = target_window["kCGWindowBounds"]
        x = int(bounds["X"])
        y = int(bounds["Y"])
        width = int(bounds["Width"])
        height = int(bounds["Height"])

        screen_width, screen_height = pyautogui.size()

        if x < 0 or y < 0 or x + width > screen_width or y + height > screen_height:
            print("  ⚠️  Window outside screen bounds, using full screen")
            return self.capture(), {
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0,
                "type": "fullscreen",
            }

        self.active_window_bounds = {"x": x, "y": y, "width": width, "height": height}

        region = (x, y, width, height)
        screenshot = self.capture(region=region)

        print(
            f"  📸 Captured {target_window.get('kCGWindowOwnerName', 'Unknown')} at ({x}, {y}, {width}x{height})"
        )

        return screenshot, self.active_window_bounds

    def _capture_active_window_windows(
        self, app_name: Optional[str] = None
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Capture active window on Windows.
        """
        # Fallback for now
        return self.capture(), {
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
            "type": "fullscreen",
        }

    def _capture_active_window_linux(
        self, app_name: Optional[str] = None
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Capture active window on Linux.
        """
        # Fallback for now
        return self.capture(), {
            "x": 0,
            "y": 0,
            "width": 0,
            "height": 0,
            "type": "fullscreen",
        }

    def window_to_screen_coords(self, x: int, y: int) -> Tuple[int, int]:
        """
        Convert window-relative coordinates to screen-absolute coordinates.

        Args:
            x, y: Coordinates relative to window

        Returns:
            (x, y) in screen coordinates
        """
        if self.active_window_bounds:
            screen_x = self.active_window_bounds["x"] + x
            screen_y = self.active_window_bounds["y"] + y
            return (screen_x, screen_y)
        return (x, y)

    def capture(
        self, region: Optional[Tuple[int, int, int, int]] = None
    ) -> Image.Image:
        """
        Capture screenshot of entire screen or specific region.

        Args:
            region: Optional region as (x, y, width, height) in SCREEN coordinates

        Returns:
            PIL Image object at full resolution
        """
        if region:
            # Scale region to screenshot coordinates
            x, y, w, h = region
            scaled_region = (
                int(x * self.scaling_factor),
                int(y * self.scaling_factor),
                int(w * self.scaling_factor),
                int(h * self.scaling_factor),
            )
            screenshot = pyautogui.screenshot(region=scaled_region)
        else:
            screenshot = pyautogui.screenshot()

        return screenshot

    def capture_as_base64(
        self, region: Optional[Tuple[int, int, int, int]] = None, format: str = "PNG"
    ) -> str:
        """
        Capture screenshot and return as base64 string.

        Args:
            region: Optional region as (x, y, width, height)
            format: Image format (PNG, JPEG, etc.)

        Returns:
            Base64 encoded screenshot
        """
        screenshot = self.capture(region=region)

        buffer = io.BytesIO()
        screenshot.save(buffer, format=format)
        buffer.seek(0)

        encoded = base64.b64encode(buffer.read()).decode("utf-8")
        return encoded

    def save(
        self, filepath: str, region: Optional[Tuple[int, int, int, int]] = None
    ) -> str:
        """
        Capture and save screenshot to file.

        Args:
            filepath: Path to save screenshot
            region: Optional region as (x, y, width, height)

        Returns:
            Path where screenshot was saved
        """
        screenshot = self.capture(region=region)
        screenshot.save(filepath)
        return filepath

    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """
        Get RGB color of pixel at specified coordinates.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            RGB tuple (r, g, b)
        """
        screenshot = self.capture()
        return screenshot.getpixel((x, y))
