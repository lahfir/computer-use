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


class TakeScreenshotTool(BaseTool):
    """Capture screenshot of screen or region."""

    name: str = "take_screenshot"
    description: str = "Capture screenshot of entire screen or specific region"
    args_schema: type[BaseModel] = TakeScreenshotInput

    def _run(self, region: Optional[dict[str, int]] = None) -> ActionResult:
        """
        Take screenshot.

        Args:
            region: Optional region to capture

        Returns:
            ActionResult with screenshot info
        """
        screenshot_tool = self._tool_registry.get_tool("screenshot")

        try:
            if region:
                image = screenshot_tool.capture_region(
                    region["x"], region["y"], region["width"], region["height"]
                )
            else:
                image = screenshot_tool.capture()

            return ActionResult(
                success=True,
                action_taken="Screenshot captured",
                method_used="screenshot",
                confidence=1.0,
                data={"size": image.size},
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
        Open application.

        Args:
            app_name: Application name

        Returns:
            ActionResult with launch details
        """
        process_tool = self._tool_registry.get_tool("process")

        try:
            result = process_tool.open_application(app_name)
            return ActionResult(
                success=result.get("success", False),
                action_taken=(
                    f"Opened {app_name}"
                    if result.get("success")
                    else f"Failed to open {app_name}"
                ),
                method_used="process",
                confidence=1.0 if result.get("success") else 0.0,
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


class ReadScreenTextTool(BaseTool):
    """Extract text from screen using OCR."""

    name: str = "read_screen_text"
    description: str = "Extract all visible text from screen or region using OCR"
    args_schema: type[BaseModel] = ReadScreenInput

    def _run(self, region: Optional[dict[str, int]] = None) -> ActionResult:
        """
        Read screen text.

        Args:
            region: Optional region to read

        Returns:
            ActionResult with extracted text
        """
        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")

        try:
            if region:
                screenshot = screenshot_tool.capture_region(
                    region["x"], region["y"], region["width"], region["height"]
                )
            else:
                screenshot = screenshot_tool.capture()

            text_results = ocr_tool.extract_all_text(screenshot)
            full_text = "\n".join([item.text for item in text_results])

            return ActionResult(
                success=True,
                action_taken="Read screen text",
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
