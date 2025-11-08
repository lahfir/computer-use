"""
Interactive GUI automation tools for CrewAI.
Complex tools: click_element (multi-tier), type_text (smart paste).
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

from ..schemas.actions import ActionResult
from ..utils.ui import console


class ClickInput(BaseModel):
    """Input for clicking an element."""

    target: str = Field(description="Element to click (e.g., 'Auto', 'Save button')")
    visual_context: Optional[str] = Field(
        default=None,
        description="CRITICAL: Spatial context REQUIRED! MUST include spatial keywords: 'top', 'bottom', 'left', 'right', 'first', 'last', 'center'. Examples: 'at top', 'bottom right', 'first button'. BAD: 'in theme options' (not spatial!). GOOD: 'theme button at top'.",
    )
    click_type: str = Field(
        default="single", description="Click type: single, double, or right"
    )
    current_app: Optional[str] = Field(
        default=None, description="Current application name for accessibility"
    )


class ClickElementTool(BaseTool):
    """
    Click element using multi-tier accuracy.
    TIER 1: Accessibility API → TIER 2: OCR
    Platform-agnostic: uses normalized coordinates from accessibility tools.
    """

    name: str = "click_element"
    description: str = """Click element using multi-tier accuracy (Accessibility API → OCR).
    Supports single, double, and right click. Works on Windows/macOS/Linux."""
    args_schema: type[BaseModel] = ClickInput

    def _run(
        self,
        target: str,
        visual_context: Optional[str] = None,
        click_type: str = "single",
        current_app: Optional[str] = None,
    ) -> ActionResult:
        """
        Click element with multi-tier approach + visual context awareness.
        Platform-agnostic implementation using normalized coordinates.

        Args:
            target: Element identifier
            visual_context: Visual/spatial context for disambiguation
            click_type: single/double/right
            current_app: Current app for accessibility

        Returns:
            ActionResult with click details
        """
        # Get tools
        screenshot_tool = self._tool_registry.get_tool("screenshot")
        accessibility_tool = self._tool_registry.get_tool("accessibility")
        ocr_tool = self._tool_registry.get_tool("ocr")
        input_tool = self._tool_registry.get_tool("input")

        # Take screenshot
        screenshot = screenshot_tool.capture()

        # Handle empty space clicks
        empty_space_keywords = [
            "empty space",
            "blank area",
            "empty area",
            "blank space",
            "background",
        ]
        target_lower = target.lower()
        is_empty_space = any(
            keyword in target_lower for keyword in empty_space_keywords
        )

        if is_empty_space and accessibility_tool and current_app:
            bounds = accessibility_tool.get_app_window_bounds(current_app)
            if bounds:
                x, y, w, h = bounds
                center_x = x + w // 2
                center_y = y + h // 2
                success = input_tool.click(center_x, center_y, validate=True)
                return ActionResult(
                    success=success,
                    action_taken=f"Clicked empty space at ({center_x}, {center_y})",
                    method_used="semantic",
                    confidence=1.0,
                    data={"coordinates": (center_x, center_y)},
                )

        # TIER 1: Accessibility API
        if accessibility_tool and accessibility_tool.available:
            console.print("    [cyan]TIER 1:[/cyan] Accessibility API")

            # TIER 1A: Native click
            if hasattr(accessibility_tool, "click_element") and current_app:
                clicked, element = accessibility_tool.click_element(target, current_app)
                if clicked:
                    return ActionResult(
                        success=True,
                        action_taken=f"Clicked {target}",
                        method_used="accessibility_native",
                        confidence=1.0,
                    )

            # TIER 1B: Find elements via accessibility (platform-agnostic)
            if current_app:
                elements = accessibility_tool.find_elements(
                    label=target, app_name=current_app
                )
                if elements:
                    elem = elements[0]
                    x, y = elem["center"]

                    if click_type == "double":
                        success = input_tool.double_click(x, y, validate=True)
                    elif click_type == "right":
                        success = input_tool.right_click(x, y, validate=True)
                    else:
                        success = input_tool.click(x, y, validate=True)

                    return ActionResult(
                        success=success,
                        action_taken=f"Clicked {target}",
                        method_used="accessibility_coordinates",
                        confidence=1.0,
                        data={"coordinates": (x, y)},
                    )

        # TIER 2: OCR
        console.print("    [cyan]TIER 2:[/cyan] OCR")
        scaling = getattr(screenshot_tool, "scaling_factor", 1.0)
        ocr_screenshot = screenshot
        x_offset = 0
        y_offset = 0

        # Crop to app window if possible
        if current_app and accessibility_tool and accessibility_tool.available:
            window_bounds = accessibility_tool.get_app_window_bounds(current_app)
            if window_bounds:
                x, y, w, h = window_bounds
                x_scaled = int(x * scaling)
                y_scaled = int(y * scaling)
                w_scaled = int(w * scaling)
                h_scaled = int(h * scaling)
                try:
                    ocr_screenshot = screenshot.crop(
                        (x_scaled, y_scaled, x_scaled + w_scaled, y_scaled + h_scaled)
                    )
                    x_offset = x
                    y_offset = y
                except Exception:
                    pass

        # OCR fuzzy find
        try:
            text_matches = ocr_tool.find_text(ocr_screenshot, target, fuzzy=True)
            if text_matches:
                element = text_matches[0]
                x_raw, y_raw = element.center
                x_screen = int(x_raw / scaling) + x_offset
                y_screen = int(y_raw / scaling) + y_offset

                if click_type == "double":
                    success = input_tool.double_click(x_screen, y_screen, validate=True)
                elif click_type == "right":
                    success = input_tool.right_click(x_screen, y_screen, validate=True)
                else:
                    success = input_tool.click(x_screen, y_screen, validate=True)

                return ActionResult(
                    success=success,
                    action_taken=f"Clicked {target}",
                    method_used="ocr",
                    confidence=element.confidence,
                    data={"coordinates": (x_screen, y_screen)},
                )
        except Exception:
            pass

        # Fuzzy matching fallback with spatial filtering
        try:
            all_text = ocr_tool.extract_all_text(ocr_screenshot)
            target_lower = target.lower().strip()

            # SPATIAL FILTERING: Use visual_context to filter candidates
            if visual_context:
                context_lower = visual_context.lower()
                screenshot_height = ocr_screenshot.height
                screenshot_width = ocr_screenshot.width

                # Filter by vertical position
                if "top" in context_lower or "above" in context_lower:
                    all_text = [
                        item
                        for item in all_text
                        if item.center[1] < screenshot_height * 0.4
                    ]
                elif "bottom" in context_lower or "below" in context_lower:
                    all_text = [
                        item
                        for item in all_text
                        if item.center[1] > screenshot_height * 0.6
                    ]
                elif "middle" in context_lower or "center" in context_lower:
                    all_text = [
                        item
                        for item in all_text
                        if screenshot_height * 0.3
                        < item.center[1]
                        < screenshot_height * 0.7
                    ]

                # Filter by horizontal position
                if "left" in context_lower:
                    all_text = [
                        item
                        for item in all_text
                        if item.center[0] < screenshot_width * 0.4
                    ]
                elif "right" in context_lower:
                    all_text = [
                        item
                        for item in all_text
                        if item.center[0] > screenshot_width * 0.6
                    ]

                # Filter by order
                if "first" in context_lower:
                    all_text = sorted(
                        all_text, key=lambda item: (item.center[1], item.center[0])
                    )[:3]
                elif "last" in context_lower:
                    all_text = sorted(
                        all_text, key=lambda item: (item.center[1], item.center[0])
                    )[-3:]

            best_match = None
            best_score = -999

            for item in all_text:
                text_lower = item.text.lower().strip()
                if text_lower == target_lower:
                    score = 1000 + item.confidence * 100
                elif text_lower.startswith(target_lower):
                    score = 700 + item.confidence * 100
                elif target_lower in text_lower:
                    score = (
                        400
                        - (len(text_lower) - len(target_lower))
                        + item.confidence * 100
                    )
                elif target_lower.startswith(text_lower) and len(text_lower) >= 3:
                    score = 300 + item.confidence * 100
                else:
                    continue

                if score > best_score:
                    best_match = item
                    best_score = score

            if best_match:
                x_raw, y_raw = best_match.center
                x_screen = int(x_raw / scaling) + x_offset
                y_screen = int(y_raw / scaling) + y_offset

                if click_type == "double":
                    success = input_tool.double_click(x_screen, y_screen, validate=True)
                elif click_type == "right":
                    success = input_tool.right_click(x_screen, y_screen, validate=True)
                else:
                    success = input_tool.click(x_screen, y_screen, validate=True)

                return ActionResult(
                    success=success,
                    action_taken=f"Clicked {target}",
                    method_used="ocr",
                    confidence=best_match.confidence,
                    data={"coordinates": (x_screen, y_screen)},
                )
        except Exception:
            pass

        return ActionResult(
            success=False,
            action_taken=f"Failed to click {target}",
            method_used="multi_tier",
            confidence=0.0,
            error=f"Could not locate: {target}",
        )


class TypeInput(BaseModel):
    """Input for typing text."""

    text: str = Field(description="Text to type")
    use_clipboard: bool = Field(default=False, description="Force clipboard paste")


class TypeTextTool(BaseTool):
    """Type text with smart paste detection and hotkey support."""

    name: str = "type_text"
    description: str = """Type text, numbers, or keyboard shortcuts.
    Smart paste for paths, URLs, long text. Supports hotkeys (cmd+c, ctrl+v)."""
    args_schema: type[BaseModel] = TypeInput

    def _run(self, text: str, use_clipboard: bool = False) -> ActionResult:
        """
        Type text with smart paste detection.

        Args:
            text: Text to type
            use_clipboard: Force paste

        Returns:
            ActionResult with typing details
        """
        if not text:
            return ActionResult(
                success=False,
                action_taken="Type failed",
                method_used="type",
                confidence=0.0,
                error="No text provided",
            )

        input_tool = self._tool_registry.get_tool("input")

        try:
            # Hotkey detection
            if "+" in text and len(text.split("+")) <= 4:
                keys = [k.strip().lower() for k in text.split("+")]
                key_map = {
                    "cmd": "command",
                    "ctrl": "ctrl",
                    "alt": "alt",
                    "shift": "shift",
                }
                mapped_keys = [key_map.get(k, k) for k in keys]
                input_tool.hotkey(*mapped_keys)
                return ActionResult(
                    success=True,
                    action_taken=f"Pressed hotkey: {text}",
                    method_used="type",
                    confidence=1.0,
                )

            # Enter key
            elif text == "\\n" or text == "\n":
                import pyautogui

                pyautogui.press("return")
                return ActionResult(
                    success=True,
                    action_taken="Pressed Enter",
                    method_used="type",
                    confidence=1.0,
                )

            # Smart paste detection
            should_paste = (
                len(text) > 50
                or text.startswith("/")
                or text.startswith("~")
                or "\\" in text
                or ("/" in text and len(text) > 20)
                or text.startswith("http://")
                or text.startswith("https://")
            )

            if use_clipboard or should_paste:
                input_tool.paste_text(text)
            else:
                input_tool.type_text(text)

            return ActionResult(
                success=True,
                action_taken=f"Typed {len(text)} chars",
                method_used="type",
                confidence=1.0,
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Type failed",
                method_used="type",
                confidence=0.0,
                error=str(e),
            )
