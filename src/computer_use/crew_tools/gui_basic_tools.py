"""
Basic GUI automation tools for CrewAI.
Simple tools: screenshot, open_application, read_screen, scroll.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

from ..schemas.actions import ActionResult


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
        import time

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

            max_attempts = 10
            wait_interval = 0.5

            for attempt in range(max_attempts):
                time.sleep(wait_interval)

                # ACTIVELY try to focus the window on each attempt
                try:
                    process_tool.focus_app(app_name)
                except Exception:
                    pass  # If focus fails, continue checking

                # Now verify the app is accessible and hopefully focused
                if process_tool and hasattr(process_tool, "is_process_running"):
                    if process_tool.is_process_running(app_name):
                        # Verify window is actually focusable
                        if accessibility_tool and hasattr(
                            accessibility_tool, "is_app_frontmost"
                        ):
                            is_front = accessibility_tool.is_app_frontmost(app_name)
                            if (
                                is_front or attempt >= 5
                            ):  # Accept after 2.5s even if not frontmost
                                return ActionResult(
                                    success=True,
                                    action_taken=f"Opened and focused {app_name} (frontmost={is_front}, attempt {attempt + 1})",
                                    method_used="process_verification+focus",
                                    confidence=1.0,
                                    data={
                                        "wait_time": (attempt + 1) * wait_interval,
                                        "is_frontmost": is_front,
                                    },
                                )
                        else:
                            # No accessibility check available, assume focused after process verified
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
        "Extract all visible text from screen, specific region, or target a specific application window using OCR. "
        "Use app_name parameter to read text from ONLY that app's window (e.g., app_name='Calculator')"
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
    """Read text from application using Accessibility API (Tier 1)."""

    name: str = "get_app_text"
    description: str = (
        "Extract text from an application using Accessibility API (100% accurate, no OCR). "
        "Perfect for reading Calculator results, text fields, labels, etc. "
        "Faster and more reliable than OCR for text-heavy applications."
    )
    args_schema: type[BaseModel] = GetAppTextInput

    def _run(self, app_name: str, role: Optional[str] = None) -> ActionResult:
        """
        Read app text via Accessibility API.

        Args:
            app_name: Application name
            role: Optional role filter

        Returns:
            ActionResult with extracted text
        """
        try:
            accessibility_tool = self._tool_registry.get_tool("accessibility")

            if not accessibility_tool:
                return ActionResult(
                    success=False,
                    action_taken="Accessibility tool not found in registry",
                    method_used="accessibility",
                    confidence=0.0,
                    error="Tool registry missing accessibility tool",
                )

            if not hasattr(accessibility_tool, "available"):
                return ActionResult(
                    success=False,
                    action_taken="Accessibility tool missing 'available' attribute",
                    method_used="accessibility",
                    confidence=0.0,
                    error="Invalid accessibility tool instance",
                )

            if not accessibility_tool.available:
                return ActionResult(
                    success=False,
                    action_taken="Accessibility API marked as unavailable",
                    method_used="accessibility",
                    confidence=0.0,
                    error="Accessibility permissions may not be granted or atomacos not installed",
                )

            texts = accessibility_tool.get_text_from_app(app_name, role)

            if texts and len(texts) > 0:
                return ActionResult(
                    success=True,
                    action_taken=f"Read {len(texts)} text values from {app_name}",
                    method_used="accessibility",
                    confidence=1.0,
                    data={"texts": texts, "count": len(texts)},
                )
            else:
                return ActionResult(
                    success=False,
                    action_taken=f"No text found in {app_name}",
                    method_used="accessibility",
                    confidence=0.0,
                    error=f"No accessible text elements found in {app_name} - app may not have text or is not focused",
                )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Exception while reading app text",
                method_used="accessibility",
                confidence=0.0,
                error=f"Exception: {str(e)}",
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
