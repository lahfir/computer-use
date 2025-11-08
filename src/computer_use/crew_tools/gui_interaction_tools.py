"""
Interactive GUI automation tools for CrewAI.
Refactored for clarity: discovery separate from execution.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional

from ..schemas.actions import ActionResult
from ..utils.ui import console
from ..utils.ocr_targeting import (
    score_ocr_candidate,
    filter_candidates_by_spatial_context,
)
from ..config.timing_config import get_timing_config


class ClickInput(BaseModel):
    """Input for clicking an element."""

    target: str = Field(description="Element to click (e.g., 'Light', 'Save button')")
    element: Optional[dict] = Field(
        default=None,
        description="Element from get_accessible_elements with 'center' [x, y]. Preferred method for accuracy.",
    )
    visual_context: Optional[str] = Field(
        default=None,
        description="Spatial context for OCR fallback only. MUST include keywords: 'top', 'bottom', 'left', 'right', 'center'. Examples: 'right side at top', 'left sidebar'.",
    )
    click_type: str = Field(
        default="single", description="Click type: single, double, or right"
    )
    current_app: Optional[str] = Field(
        default=None, description="Current application name (for window cropping)"
    )


class ClickElementTool(BaseTool):
    """
    Click element using element coordinates or OCR fallback.
    Preferred: Use get_accessible_elements first, then pass element dict.
    Fallback: OCR with visual_context for spatial disambiguation.
    CRITICAL: Always provide current_app for accurate window-relative coordinates.
    """

    name: str = "click_element"
    description: str = """Click element using coordinates or OCR.
    PREFERRED: Pass element dict from get_accessible_elements.
    FALLBACK: OCR with visual_context (spatial keywords required).
    CRITICAL: Always provide current_app parameter for accurate window-relative clicks."""
    args_schema: type[BaseModel] = ClickInput

    def _run(
        self,
        target: str,
        element: Optional[dict] = None,
        visual_context: Optional[str] = None,
        click_type: str = "single",
        current_app: Optional[str] = None,
    ) -> ActionResult:
        """
        Click element with simplified logic.

        Args:
            target: Element identifier (for logging)
            element: Element dict with 'center' [x, y] (preferred)
            visual_context: Spatial context for OCR fallback
            click_type: single/double/right
            current_app: Current app for window cropping

        Returns:
            ActionResult with click details
        """
        input_tool = self._tool_registry.get_tool("input")

        if element and "center" in element:
            console.print("    [cyan]TIER 1:[/cyan] Element coordinates")
            center = element["center"]
            if isinstance(center, list) and len(center) == 2:
                x, y = center
                console.print(f"    [green]Clicking {target} at ({x}, {y})[/green]")

                if click_type == "double":
                    success = input_tool.double_click(x, y, validate=True)
                elif click_type == "right":
                    success = input_tool.right_click(x, y, validate=True)
                else:
                    success = input_tool.click(x, y, validate=True)

                import time

                timing = get_timing_config()
                time.sleep(timing.ui_state_change_delay)
                console.print(
                    f"    [dim]⏱️  Waited {timing.ui_state_change_delay}s for UI state change[/dim]"
                )

                return ActionResult(
                    success=success,
                    action_taken=f"Clicked {target}",
                    method_used="element_coordinates",
                    confidence=1.0,
                    data={"coordinates": (x, y)},
                )

        console.print("    [cyan]TIER 2:[/cyan] OCR fallback")

        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        # CRITICAL: Warn if current_app not provided
        if not current_app:
            console.print(
                "    [yellow]⚠️  WARNING: current_app not provided! Using full screen coordinates. This will likely fail![/yellow]"
            )

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

        # Check score threshold
        MIN_VIABLE_SCORE = 500.0
        if not best_match or best_score < MIN_VIABLE_SCORE:
            console.print(
                f"    [red]No reliable OCR target for '{target}'. Best score: {best_score:.2f}[/red]"
            )
            return ActionResult(
                success=False,
                action_taken=f"Failed to click {target}",
                method_used="ocr",
                confidence=0.0,
                error=f"No reliable OCR match for '{target}' (score {best_score:.2f} < {MIN_VIABLE_SCORE}). Suggestion: Use get_window_image for visual analysis or get_accessible_elements for element discovery.",
            )

        x_raw, y_raw = best_match.center
        x_screen = int(x_raw / scaling) + x_offset
        y_screen = int(y_raw / scaling) + y_offset

        console.print(
            f"    [green]Clicking '{best_match.text}' (score {best_score:.1f}) at ({x_screen}, {y_screen})[/green]"
        )

        if click_type == "double":
            success = input_tool.double_click(x_screen, y_screen, validate=True)
        elif click_type == "right":
            success = input_tool.right_click(x_screen, y_screen, validate=True)
        else:
            success = input_tool.click(x_screen, y_screen, validate=True)

        import time

        timing = get_timing_config()
        time.sleep(timing.ui_state_change_delay)
        console.print(
            f"    [dim]⏱️  Waited {timing.ui_state_change_delay}s for UI state change[/dim]"
        )

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
