"""
Interactive GUI automation tools for CrewAI.
Refactored for clarity: discovery separate from execution.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

from ..schemas.actions import ActionResult
from ..utils.ui import action_spinner, dashboard, print_action_result
from ..utils.ocr_targeting import (
    score_ocr_candidate,
    filter_candidates_by_spatial_context,
)
from ..config.timing_config import get_timing_config


def check_cancellation() -> Optional[ActionResult]:
    """
    Check if task cancellation has been requested.
    Returns ActionResult with cancellation error if cancelled, None otherwise.
    """
    from ..crew import ComputerUseCrew

    if ComputerUseCrew.is_cancelled():
        return ActionResult(
            success=False,
            action_taken="Task cancelled by user",
            method_used="cancellation",
            confidence=0.0,
            error="Task cancelled by user (ESC pressed)",
        )
    return None


class ClickInput(BaseModel):
    """Input for clicking an element."""

    target: Optional[str] = Field(
        default="element",
        description="Element to click (e.g., 'Light', 'Save button'). Optional when element_id is provided.",
    )
    element_id: Optional[str] = Field(
        default=None,
        description="Unique element ID from get_accessible_elements. BEST method - uses native click.",
    )
    element: Optional[dict] = Field(
        default=None,
        description="Element dict with 'center' [x, y]. Use element_id instead when available.",
    )
    visual_context: Optional[str] = Field(
        default=None,
        description="Spatial context for OCR fallback only.",
    )
    click_type: str = Field(
        default="single", description="Click type: single, double, or right"
    )
    current_app: Optional[str] = Field(
        default=None, description="Current application name"
    )


class ClickElementTool(BaseTool):
    """
    Click element using native accessibility or OCR fallback.

    BEST: Pass element_id from get_accessible_elements (native click, 100% accurate)
    FALLBACK: Pass element dict with center coordinates
    LAST RESORT: OCR with visual_context
    """

    name: str = "click_element"
    description: str = """Click element.
    BEST: element_id='<id>' from get_accessible_elements (native click, no duplicates)
    FALLBACK: element=<dict with center>
    LAST: OCR with target and visual_context"""
    args_schema: type[BaseModel] = ClickInput

    def _run(
        self,
        target: Optional[str] = "element",
        element_id: Optional[str] = None,
        element: Optional[dict] = None,
        visual_context: Optional[str] = None,
        click_type: str = "single",
        current_app: Optional[str] = None,
    ) -> ActionResult:
        """
        Click element with priority: element_id > element > OCR.

        Args:
            target: Element label (for logging/fallback)
            element_id: Unique ID from get_accessible_elements (best method)
            element: Element dict with 'center' [x, y]
            visual_context: Spatial context for OCR fallback
            click_type: single/double/right
            current_app: Current app name

        Returns:
            ActionResult with click details
        """
        if cancelled := check_cancellation():
            return cancelled

        target = target or "element"
        dashboard.set_action("Clicking", target)

        accessibility_tool = self._tool_registry.get_tool("accessibility")

        if not element_id and element and isinstance(element, dict):
            element_id = element.get("element_id")

        if element_id and accessibility_tool and accessibility_tool.available:
            if hasattr(accessibility_tool, "click_by_id"):
                with action_spinner("Clicking", target):
                    success, message = accessibility_tool.click_by_id(element_id)

                    if click_type == "double":
                        elem = accessibility_tool.get_element_by_id(element_id)
                        if elem and elem.get("center"):
                            x, y = elem["center"]
                            input_tool = self._tool_registry.get_tool("input")
                            input_tool.double_click(x, y)
                    elif click_type == "right":
                        elem = accessibility_tool.get_element_by_id(element_id)
                        if elem and elem.get("center"):
                            x, y = elem["center"]
                            input_tool = self._tool_registry.get_tool("input")
                            input_tool.right_click(x, y)

                print_action_result(success, message)

                return ActionResult(
                    success=success,
                    action_taken=message,
                    method_used="accessibility_native",
                    confidence=1.0 if success else 0.0,
                )

        input_tool = self._tool_registry.get_tool("input")

        if element and "center" in element:
            center = element["center"]
            if isinstance(center, list) and len(center) == 2:
                x, y = center

                with action_spinner("Clicking", target):
                    if click_type == "double":
                        success = input_tool.double_click(x, y, validate=True)
                    elif click_type == "right":
                        success = input_tool.right_click(x, y, validate=True)
                    else:
                        success = input_tool.click(x, y, validate=True)

                    import time

                    timing = get_timing_config()
                    time.sleep(timing.ui_state_change_delay)

                accessibility_tool = self._tool_registry.get_tool("accessibility")
                if accessibility_tool and hasattr(
                    accessibility_tool, "invalidate_cache"
                ):
                    accessibility_tool.invalidate_cache()

                print_action_result(success, f"Clicked {target}")

                return ActionResult(
                    success=success,
                    action_taken=f"Clicked {target}",
                    method_used="element_coordinates",
                    confidence=1.0,
                    data={"coordinates": (x, y)},
                )

        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        screenshot = screenshot_tool.capture()
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

        candidates = []
        try:
            exact_matches = ocr_tool.find_text(ocr_screenshot, target, fuzzy=False)
            if exact_matches:
                candidates.extend(exact_matches)
            else:
                fuzzy_matches = ocr_tool.find_text(ocr_screenshot, target, fuzzy=True)
                if fuzzy_matches:
                    candidates.extend(fuzzy_matches)
        except Exception:
            pass

        # Add all text for comprehensive scoring
        try:
            all_text = ocr_tool.extract_all_text(ocr_screenshot) or []
            existing_ids = {id(item) for item in candidates}
            candidates.extend(item for item in all_text if id(item) not in existing_ids)
        except Exception:
            pass

        if not candidates:
            return ActionResult(
                success=False,
                action_taken=f"Failed to click {target}",
                method_used="ocr",
                confidence=0.0,
                error=f"No OCR text found for '{target}'. Consider using get_window_image for visual analysis.",
            )

        # Apply spatial filtering if visual_context provided
        if visual_context:
            candidates = filter_candidates_by_spatial_context(
                candidates, visual_context, ocr_screenshot.width, ocr_screenshot.height
            )

        # Score all candidates
        target_lower = target.lower().strip()
        best_match = None
        best_score = -999.0

        for item in candidates:
            score, relation = score_ocr_candidate(
                item,
                target_lower,
                ocr_screenshot.width,
                ocr_screenshot.height,
                visual_context,
            )
            if score > best_score:
                best_match = item
                best_score = score

        MIN_VIABLE_SCORE = 500.0
        if not best_match or best_score < MIN_VIABLE_SCORE:
            print_action_result(False, f"No OCR match for '{target}'")
            return ActionResult(
                success=False,
                action_taken=f"Failed to click {target}",
                method_used="ocr",
                confidence=0.0,
                error=f"No reliable OCR match for '{target}'. Use get_window_image or get_accessible_elements.",
            )

        x_raw, y_raw = best_match.center
        x_screen = int(x_raw / scaling) + x_offset
        y_screen = int(y_raw / scaling) + y_offset

        with action_spinner("Clicking", best_match.text):
            if click_type == "double":
                success = input_tool.double_click(x_screen, y_screen, validate=True)
            elif click_type == "right":
                success = input_tool.right_click(x_screen, y_screen, validate=True)
            else:
                success = input_tool.click(x_screen, y_screen, validate=True)

            import time

            timing = get_timing_config()
            time.sleep(timing.ui_state_change_delay)

        print_action_result(success, "Clicked via OCR")

        return ActionResult(
            success=success,
            action_taken=f"Clicked {target}",
            method_used="ocr",
            confidence=best_match.confidence,
            data={
                "coordinates": (x_screen, y_screen),
                "matched_text": best_match.text,
                "score": best_score,
            },
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

        display_text = text[:20] + "..." if len(text) > 20 else text
        dashboard.set_action("Typing", display_text)

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
