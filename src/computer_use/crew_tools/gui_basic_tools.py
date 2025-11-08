"""
Basic GUI automation tools for CrewAI.
Simple tools: screenshot, open_application, read_screen, scroll.
"""

import atexit
import os
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, Set

from ..schemas.actions import ActionResult
from ..config.timing_config import get_timing_config


class TempFileRegistry:
    """
    Registry to track and cleanup temporary files created by tools.
    Ensures all temp files are deleted when the program exits.
    """

    _temp_files: Set[str] = set()

    @classmethod
    def register(cls, filepath: str) -> None:
        """Register a temporary file for cleanup."""
        cls._temp_files.add(filepath)

    @classmethod
    def cleanup(cls) -> None:
        """Delete all registered temporary files."""
        for filepath in cls._temp_files:
            try:
                if os.path.exists(filepath):
                    os.unlink(filepath)
            except Exception:
                pass  # Silently ignore cleanup errors
        cls._temp_files.clear()

    @classmethod
    def cleanup_file(cls, filepath: str) -> None:
        """Delete a specific temporary file immediately."""
        try:
            if os.path.exists(filepath):
                os.unlink(filepath)
            cls._temp_files.discard(filepath)
        except Exception:
            pass  # Silently ignore cleanup errors


# Register cleanup on program exit
atexit.register(TempFileRegistry.cleanup)


class TakeScreenshotInput(BaseModel):
    """Input for taking a screenshot."""

    region: Optional[dict[str, int]] = Field(
        default=None, description="Optional region: {x, y, width, height}"
    )
    app_name: Optional[str] = Field(
        default=None,
        description="Optional app name to capture only that application's window",
    )


class TakeScreenshotTool(BaseTool):
    """Capture screenshot of screen or region."""

    name: str = "take_screenshot"
    description: str = (
        "Capture screenshot of entire screen, specific region, or target a specific application window. "
        "Use app_name parameter to capture ONLY that app's window (e.g., app_name='Calculator')"
    )
    args_schema: type[BaseModel] = TakeScreenshotInput

    def _run(
        self, region: Optional[dict[str, int]] = None, app_name: Optional[str] = None
    ) -> ActionResult:
        """
        Take screenshot.

        Args:
            region: Optional region to capture
            app_name: Optional app name to capture only that window

        Returns:
            ActionResult with screenshot info
        """
        screenshot_tool = self._tool_registry.get_tool("screenshot")

        try:
            if app_name:
                try:
                    image, bounds = screenshot_tool.capture_active_window(app_name)
                    return ActionResult(
                        success=True,
                        action_taken=f"Screenshot captured of {app_name} window at {bounds}",
                        method_used="screenshot_window",
                        confidence=1.0,
                        data={
                            "size": image.size,
                            "bounds": bounds,
                            "app_name": app_name,
                            "captured_window": True,
                        },
                    )
                except RuntimeError as e:
                    return ActionResult(
                        success=False,
                        action_taken=f"Failed to capture {app_name} window",
                        method_used="screenshot_window",
                        confidence=0.0,
                        error=str(e),
                        data={"app_name": app_name, "captured_window": False},
                    )
            elif region:
                region_tuple = (
                    region["x"],
                    region["y"],
                    region["width"],
                    region["height"],
                )
                image = screenshot_tool.capture(region=region_tuple)
            else:
                image = screenshot_tool.capture()

            return ActionResult(
                success=True,
                action_taken="Screenshot captured (full screen)",
                method_used="screenshot_fullscreen",
                confidence=1.0,
                data={"size": image.size, "captured_window": False},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Screenshot failed",
                method_used="screenshot",
                confidence=0.0,
                error=str(e),
            )


class OpenAppInput(BaseModel):
    """Input for opening an application."""

    app_name: str = Field(description="Application name to open")


class OpenApplicationTool(BaseTool):
    """Open desktop application."""

    name: str = "open_application"
    description: str = "Open desktop application by name (e.g., Calculator, Safari)"
    args_schema: type[BaseModel] = OpenAppInput

    def _run(self, app_name: str) -> ActionResult:
        """
        Open application and WAIT for it to become active window.

        Args:
            app_name: Application name

        Returns:
            ActionResult with launch details
        """

        process_tool = self._tool_registry.get_tool("process")
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        try:
            result = process_tool.open_application(app_name)
            if not result.get("success", False):
                return ActionResult(
                    success=False,
                    action_taken=f"Failed to launch {app_name}",
                    method_used="process",
                    confidence=0.0,
                    error=result.get("message", "Launch failed"),
                )

            timing = get_timing_config()
            max_attempts = timing.app_launch_max_attempts
            wait_interval = timing.app_launch_retry_interval

            for attempt in range(max_attempts):
                try:
                    process_tool.focus_app(app_name)
                except Exception:
                    pass  # If focus fails, continue checking

                if process_tool and hasattr(process_tool, "is_process_running"):
                    if process_tool.is_process_running(app_name):
                        if accessibility_tool and hasattr(
                            accessibility_tool, "is_app_frontmost"
                        ):
                            is_front = accessibility_tool.is_app_frontmost(app_name)
                            if (
                                is_front
                                or attempt >= timing.app_launch_frontmost_attempts
                            ):
                                if hasattr(accessibility_tool, "set_active_app"):
                                    accessibility_tool.set_active_app(app_name)

                                return ActionResult(
                                    success=True,
                                    action_taken=f"Opened and focused {app_name} (frontmost={is_front}, attempt {attempt + 1})",
                                    method_used="process_verification+focus",
                                    confidence=1.0,
                                    data={
                                        "wait_time": (attempt + 1) * wait_interval
                                        + 1.0,
                                        "is_frontmost": is_front,
                                    },
                                )
                        else:
                            return ActionResult(
                                success=True,
                                action_taken=f"Opened {app_name} (process verified, attempt {attempt + 1})",
                                method_used="process_verification",
                                confidence=1.0,
                                data={"wait_time": (attempt + 1) * wait_interval},
                            )

                if accessibility_tool and hasattr(accessibility_tool, "is_app_running"):
                    if accessibility_tool.is_app_running(app_name):
                        return ActionResult(
                            success=True,
                            action_taken=f"Opened {app_name} (accessibility verified, attempt {attempt + 1})",
                            method_used="accessibility_verification",
                            confidence=1.0,
                            data={"wait_time": (attempt + 1) * wait_interval},
                        )

                screenshot_tool = self._tool_registry.get_tool("screenshot")
                if screenshot_tool:
                    try:
                        _, metadata = screenshot_tool.capture_active_window(app_name)
                        if metadata.get("captured"):
                            return ActionResult(
                                success=True,
                                action_taken=f"Opened {app_name} (window captured, attempt {attempt + 1})",
                                method_used="window_capture_verification",
                                confidence=1.0,
                                data={"wait_time": (attempt + 1) * wait_interval},
                            )
                    except Exception:
                        pass

            # Timeout: app launched but couldn't verify it's accessible
            return ActionResult(
                success=False,
                action_taken=f"Launched {app_name} but couldn't verify it's running after 5s",
                method_used="process",
                confidence=0.3,
                error=f"{app_name} launch command executed but app not detected within timeout",
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken=f"Failed to open {app_name}",
                method_used="process",
                confidence=0.0,
                error=str(e),
            )


class ReadScreenInput(BaseModel):
    """Input for reading screen text."""

    region: Optional[dict[str, int]] = Field(
        default=None, description="Optional region: {x, y, width, height}"
    )
    app_name: Optional[str] = Field(
        default=None,
        description="Optional app name to read text from only that application's window",
    )


class ReadScreenTextTool(BaseTool):
    """Extract text from screen using OCR."""

    name: str = "read_screen_text"
    description: str = (
        "Extract visible text from screen, specific region, or application window using OCR. "
        "Can target entire screen, custom region, or specific application."
    )
    args_schema: type[BaseModel] = ReadScreenInput

    def _run(
        self, region: Optional[dict[str, int]] = None, app_name: Optional[str] = None
    ) -> ActionResult:
        """
        Read screen text.

        Args:
            region: Optional region to read
            app_name: Optional app name to read text from only that window

        Returns:
            ActionResult with extracted text
        """
        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")

        try:
            if app_name:
                try:
                    screenshot, bounds = screenshot_tool.capture_active_window(app_name)
                    if not bounds.get("captured"):
                        return ActionResult(
                            success=False,
                            action_taken=f"Failed to capture {app_name} window - window may not be active or visible",
                            method_used="ocr",
                            confidence=0.0,
                            error=f"{app_name} window not found or not in foreground",
                        )
                except RuntimeError as e:
                    return ActionResult(
                        success=False,
                        action_taken=f"Failed to capture {app_name} window",
                        method_used="ocr",
                        confidence=0.0,
                        error=str(e),
                    )
            elif region:
                region_tuple = (
                    region["x"],
                    region["y"],
                    region["width"],
                    region["height"],
                )
                screenshot = screenshot_tool.capture(region=region_tuple)
            else:
                screenshot = screenshot_tool.capture()

            text_results = ocr_tool.extract_all_text(screenshot)
            full_text = "\n".join([item.text for item in text_results])

            if not text_results or len(full_text.strip()) == 0:
                return ActionResult(
                    success=False,
                    action_taken=f"Read {app_name or 'screen'} but found no text",
                    method_used="ocr",
                    confidence=0.0,
                    error="No text detected in captured area - window may be blank or not focused",
                )

            return ActionResult(
                success=True,
                action_taken=(
                    f"Read text from {app_name} window"
                    if app_name
                    else "Read screen text"
                ),
                method_used="ocr",
                confidence=1.0,
                data={"text": full_text[:500], "count": len(text_results)},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Failed to read screen",
                method_used="ocr",
                confidence=0.0,
                error=str(e),
            )


class GetAppTextInput(BaseModel):
    """Input for reading app text via Accessibility API."""

    app_name: str = Field(description="Application name to read text from")
    role: Optional[str] = Field(
        default=None,
        description="Optional role filter (StaticText, TextField, etc.)",
    )


class GetAppTextTool(BaseTool):
    """Read text from application using Accessibility API with OCR fallback."""

    name: str = "get_app_text"
    description: str = (
        "Extract text from an application using Accessibility API first, "
        "with automatic fallback to OCR if accessibility is unavailable. "
        "Returns all text found in the application."
    )
    args_schema: type[BaseModel] = GetAppTextInput

    def _run(self, app_name: str, role: Optional[str] = None) -> ActionResult:
        """
        Read app text via Accessibility API with OCR fallback.

        Args:
            app_name: Application name
            role: Optional role filter

        Returns:
            ActionResult with extracted text
        """
        try:
            accessibility_tool = self._tool_registry.get_tool("accessibility")

            if not accessibility_tool:
                return self._fallback_to_ocr(app_name)

            if not hasattr(accessibility_tool, "available"):
                return self._fallback_to_ocr(app_name)

            if not accessibility_tool.available:
                return self._fallback_to_ocr(app_name)

            texts = accessibility_tool.get_text_from_app(app_name, role)

            if not texts or len(texts) == 0:
                return self._fallback_to_ocr(app_name)

                return ActionResult(
                    success=True,
                    action_taken=f"Read {len(texts)} text values from {app_name}",
                    method_used="accessibility",
                    confidence=1.0,
                    data={"texts": texts, "count": len(texts)},
                )

        except Exception as e:
            return self._fallback_to_ocr(app_name, error=str(e))

    def _fallback_to_ocr(
        self, app_name: str, error: Optional[str] = None
    ) -> ActionResult:
        """
        Fallback to OCR when accessibility is unavailable.

        Args:
            app_name: Application name
            error: Optional error message

        Returns:
            ActionResult from OCR reading
        """
        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")

        try:
            screenshot, bounds = screenshot_tool.capture_active_window(app_name)
            if not bounds.get("captured"):
                return ActionResult(
                    success=False,
                    action_taken=f"Failed to read {app_name} - window not found",
                    method_used="ocr_fallback",
                    confidence=0.0,
                    error=f"{app_name} window not found or not in foreground",
                )

            text_results = ocr_tool.extract_all_text(screenshot)
            full_text = "\n".join([item.text for item in text_results])

            if not text_results or len(full_text.strip()) == 0:
                return ActionResult(
                    success=False,
                    action_taken=f"No text found in {app_name}",
                    method_used="ocr_fallback",
                    confidence=0.0,
                    error="No text detected in captured area",
                )

            texts = [line.strip() for line in full_text.split("\n") if line.strip()]

            return ActionResult(
                success=True,
                action_taken=f"Read {len(texts)} text values from {app_name} (via OCR)",
                method_used="ocr_fallback",
                confidence=0.9,
                data={"texts": texts, "count": len(texts)},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken=f"Failed to read {app_name}",
                method_used="ocr_fallback",
                confidence=0.0,
                error=f"OCR fallback failed: {str(e)}",
            )


class ScrollInput(BaseModel):
    """Input for scrolling."""

    direction: str = Field(default="down", description="Scroll direction: up or down")
    amount: int = Field(default=3, description="Scroll amount")


class ScrollTool(BaseTool):
    """Scroll screen up or down."""

    name: str = "scroll"
    description: str = "Scroll screen up or down"
    args_schema: type[BaseModel] = ScrollInput

    def _run(self, direction: str = "down", amount: int = 3) -> ActionResult:
        """
        Scroll screen.

        Args:
            direction: up or down
            amount: Scroll units

        Returns:
            ActionResult with scroll details
        """
        input_tool = self._tool_registry.get_tool("input")

        try:
            if direction == "down":
                input_tool.scroll(-amount)
            else:
                input_tool.scroll(amount)

            return ActionResult(
                success=True,
                action_taken=f"Scrolled {direction}",
                method_used="scroll",
                confidence=1.0,
                data={"direction": direction},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Scroll failed",
                method_used="scroll",
                confidence=0.0,
                error=str(e),
            )


class ListRunningAppsInput(BaseModel):
    """Input for listing running applications."""

    pass


class ListRunningAppsTool(BaseTool):
    """List all currently running applications."""

    name: str = "list_running_apps"
    description: str = (
        "Get list of all currently running applications. "
        "Use this BEFORE trying to open an app to check if it's already running. "
        "Returns list of app names that are currently active."
    )
    args_schema: type[BaseModel] = ListRunningAppsInput

    def _run(self) -> ActionResult:
        """
        Get list of running applications.

        Returns:
            ActionResult with list of running app names
        """
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        if not accessibility_tool or not accessibility_tool.available:
            return ActionResult(
                success=False,
                action_taken="Cannot list apps",
                method_used="accessibility",
                confidence=0.0,
                error="Accessibility API not available",
            )

        try:
            running_apps = accessibility_tool.get_running_app_names()

            if running_apps:
                return ActionResult(
                    success=True,
                    action_taken=f"Found {len(running_apps)} running applications",
                    method_used="accessibility",
                    confidence=1.0,
                    data={"running_apps": running_apps, "count": len(running_apps)},
                )
            else:
                return ActionResult(
                    success=False,
                    action_taken="No running apps found",
                    method_used="accessibility",
                    confidence=0.0,
                    error="Could not retrieve running applications",
                )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Failed to list running apps",
                method_used="accessibility",
                confidence=0.0,
                error=str(e),
            )


class CheckAppRunningInput(BaseModel):
    """Input for checking if an app is running."""

    app_name: str = Field(description="Application name to check")


class CheckAppRunningTool(BaseTool):
    """Check if a specific application is currently running."""

    name: str = "check_app_running"
    description: str = (
        "Check if a specific application is currently running. "
        "Use this to verify an app's state before trying to open or interact with it. "
        "Returns true if app is running, false otherwise."
    )
    args_schema: type[BaseModel] = CheckAppRunningInput

    def _run(self, app_name: str) -> ActionResult:
        """
        Check if app is running.

        Args:
            app_name: Application name to check

        Returns:
            ActionResult indicating if app is running
        """
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        if not accessibility_tool or not accessibility_tool.available:
            return ActionResult(
                success=False,
                action_taken="Cannot check app status",
                method_used="accessibility",
                confidence=0.0,
                error="Accessibility API not available",
            )

        try:
            is_running = accessibility_tool.is_app_running(app_name)

            return ActionResult(
                success=True,
                action_taken=f"Checked if {app_name} is running",
                method_used="accessibility",
                confidence=1.0,
                data={"app_name": app_name, "is_running": is_running},
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken=f"Failed to check {app_name} status",
                method_used="accessibility",
                confidence=0.0,
                error=str(e),
            )


class GetAccessibleElementsInput(BaseModel):
    """Input for getting all accessible elements."""

    app_name: str = Field(description="Application name to get elements from")


class GetAccessibleElementsTool(BaseTool):
    """
    Get all interactive elements from an application using Accessibility API.
    Returns a structured list of clickable elements with their coordinates.
    """

    name: str = "get_accessible_elements"
    description: str = (
        "Get all interactive UI elements from an application using Accessibility API. "
        "Returns a list of elements with label, role, bounds, and center coordinates. "
        "Use this to discover available clickable elements before clicking."
    )
    args_schema: type[BaseModel] = GetAccessibleElementsInput

    def _run(self, app_name: str) -> ActionResult:
        """
        Get all accessible elements from app using comprehensive UI element detection.

        Args:
            app_name: Application name

        Returns:
            ActionResult with categorized list of elements
        """
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        if not accessibility_tool or not accessibility_tool.available:
            return ActionResult(
                success=True,
                action_taken=f"Accessibility not available for {app_name}",
                method_used="accessibility",
                confidence=0.0,
                data={
                    "elements": [],
                    "count": 0,
                    "reason": "Accessibility API unavailable",
                },
            )

        try:
            elements = []
            if hasattr(accessibility_tool, "get_all_ui_elements"):
                categorized = accessibility_tool.get_all_ui_elements(app_name)
                all_elements = []
                for category, items in categorized.items():
                    all_elements.extend(items)

                if not all_elements:
                    elements = accessibility_tool.get_all_interactive_elements(app_name)
                else:
                    elements = all_elements
            else:
                elements = accessibility_tool.get_all_interactive_elements(app_name)

            if not elements:
                return ActionResult(
                    success=True,
                    action_taken=f"No interactive elements found in {app_name} after retries",
                    method_used="accessibility",
                    confidence=1.0,
                    data={"elements": [], "count": 0},
                )

            window_bounds = None
            if hasattr(accessibility_tool, "get_app_window_bounds"):
                window_bounds = accessibility_tool.get_app_window_bounds(app_name)

            timing = get_timing_config()
            window_y_start = window_bounds[1] if window_bounds else 0
            window_height = (
                window_bounds[3] if window_bounds else timing.default_window_height
            )

            top_third = window_y_start + (window_height / 3)
            bottom_third = window_y_start + (2 * window_height / 3)

            normalized_elements = []
            for elem in elements:
                bounds = list(elem.get("bounds", []))
                center = list(elem.get("center", []))

                spatial_hint = ""
                if center and len(center) >= 2 and window_bounds:
                    y_pos = center[1]
                    if y_pos < top_third:
                        spatial_hint = " [TOP]"
                    elif y_pos < bottom_third:
                        spatial_hint = " [MIDDLE]"
                    else:
                        spatial_hint = " [BOTTOM]"

                normalized = {
                    "label": elem.get("label", "") + spatial_hint,
                    "title": elem.get("title", "") + spatial_hint,
                    "role": elem.get("role", ""),
                    "identifier": elem.get("identifier", ""),
                    "bounds": bounds,
                    "center": center,
                    "category": elem.get("category", "interactive"),
                }
                normalized_elements.append(normalized)

            normalized_elements.sort(
                key=lambda e: (
                    e["center"][1] if e["center"] else 9999,
                    e["center"][0] if e["center"] else 9999,
                )
            )

            return ActionResult(
                success=True,
                action_taken=f"Found {len(normalized_elements)} UI elements in {app_name}",
                method_used="accessibility",
                confidence=1.0,
                data={
                    "elements": normalized_elements,
                    "count": len(normalized_elements),
                },
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken=f"Failed to get elements from {app_name}",
                method_used="accessibility",
                confidence=0.0,
                error=str(e),
            )


class GetWindowImageInput(BaseModel):
    """Input for getting window image."""

    app_name: Optional[str] = Field(
        default=None,
        description="Application name to capture. If not provided, captures full screen",
    )
    region: Optional[dict[str, int]] = Field(
        default=None,
        description="Optional region to crop: {x, y, width, height}",
    )
    element: Optional[dict] = Field(
        default=None,
        description="Optional element to crop by its bounds [x, y, w, h]",
    )


class GetWindowImageTool(BaseTool):
    """
    Get window image as base64 for vision analysis (on-demand, cost-aware).
    Only call this when OCR and accessibility are insufficient.
    """

    name: str = "get_window_image"
    description: str = (
        "Get base64-encoded image of a window, region, or element for vision analysis. "
        "COST-AWARE: Only use when OCR/accessibility are insufficient. "
        "Returns base64 PNG image and file path. "
        "Use for: ambiguous UI elements, spatial reasoning, multi-panel layouts."
    )
    args_schema: type[BaseModel] = GetWindowImageInput

    def _run(
        self,
        app_name: Optional[str] = None,
        region: Optional[dict[str, int]] = None,
        element: Optional[dict] = None,
    ) -> ActionResult:
        """
        Get window image as base64.

        Args:
            app_name: Application name to capture
            region: Optional region to crop
            element: Optional element with bounds to crop

        Returns:
            ActionResult with base64 image data
        """
        import tempfile

        screenshot_tool = self._tool_registry.get_tool("screenshot")

        try:
            # Determine what to capture
            if element and "bounds" in element and len(element["bounds"]) == 4:
                # Crop by element bounds
                x, y, w, h = element["bounds"]
                region_tuple = (x, y, w, h)
                image = screenshot_tool.capture(region=region_tuple)
                capture_type = f"element at ({x},{y})"
            elif app_name:
                # Capture application window
                image, bounds = screenshot_tool.capture_active_window(app_name)
                capture_type = f"{app_name} window"
            elif region:
                # Capture specific region
                region_tuple = (
                    region["x"],
                    region["y"],
                    region["width"],
                    region["height"],
                )
                image = screenshot_tool.capture(region=region_tuple)
                capture_type = f"region {region_tuple}"
            else:
                # Full screen capture
                image = screenshot_tool.capture()
                capture_type = "full screen"

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".png", delete=False
            ) as tmp:
                image.save(tmp, format="PNG")
                temp_path = tmp.name

            # Register temp file for cleanup
            TempFileRegistry.register(temp_path)

            return ActionResult(
                success=True,
                action_taken=f"Captured {capture_type} as image. Image saved to {temp_path} for vision analysis.",
                method_used="screenshot",
                confidence=1.0,
                data={
                    "path": temp_path,
                    "size": list(image.size),
                    "app_name": app_name,
                    "note": "Image saved to file. Use vision model to analyze if needed.",
                },
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Failed to capture window image",
                method_used="screenshot",
                confidence=0.0,
                error=str(e),
            )


class RequestHumanInputInput(BaseModel):
    """Input for requesting human input/decision."""

    question: str = Field(
        description="The question to ask the user (e.g., 'A dialog appeared with options: Replace, Keep Both, Cancel. Which option should I choose?')"
    )
    context: str = Field(
        description="Additional context about the situation (e.g., 'Pasting file into Downloads folder')"
    )


class RequestHumanInputTool(BaseTool):
    """Request human input for ambiguous decisions or dialog choices."""

    name: str = "request_human_input"
    description: str = (
        "Request human input when encountering ambiguous situations like dialogs with multiple options "
        "(Replace/Keep Both/Cancel), unclear user intent, or decisions that require user preference. "
        "Use this when you detect a dialog popup asking for user decision. "
        "DO NOT use this for simple yes/no confirmations - only for ambiguous multi-option scenarios."
    )
    args_schema: type[BaseModel] = RequestHumanInputInput

    def _run(self, question: str, context: str) -> ActionResult:
        """
        Request human input for a decision.

        Args:
            question: The question to ask the user
            context: Additional context about the situation

        Returns:
            ActionResult with user's response
        """
        from rich.console import Console
        from rich.panel import Panel

        console = Console()

        # Display the request
        console.print()
        console.print(
            Panel(
                f"[bold yellow]🤔 Human Input Needed[/bold yellow]\n\n"
                f"[bold]Context:[/bold] {context}\n\n"
                f"[bold]Question:[/bold] {question}\n\n"
                f"[dim]Please type your response below:[/dim]",
                title="⚠️  Agent Requesting Input",
                border_style="yellow",
            )
        )

        try:
            import sys

            sys.stdout.flush()
            sys.stderr.flush()

            separator = "=" * 80
            print(f"\n{separator}")
            print("🤖 AGENT NEEDS YOUR INPUT:")
            print(f"CONTEXT: {context}")
            print(f"QUESTION: {question}")
            print(separator)
            print("Please type your response and press Enter:")
            sys.stdout.flush()

            user_response = input("> ").strip()

            if not user_response:
                print("⚠️  Empty response received, treating as cancellation")
                return ActionResult(
                    success=False,
                    action_taken="Requested human input",
                    method_used="human_input",
                    confidence=0.0,
                    error="User provided empty response",
                )

            print(f"✅ Received: {user_response}\n")
            return ActionResult(
                success=True,
                action_taken=f"Received human input: {user_response}",
                method_used="human_input",
                confidence=1.0,
                data={"question": question, "response": user_response},
            )

        except (KeyboardInterrupt, EOFError) as e:
            print(f"\n⚠️  Input cancelled: {e}")
            return ActionResult(
                success=False,
                action_taken="User cancelled input request",
                method_used="human_input",
                confidence=0.0,
                error="User cancelled the task",
            )
