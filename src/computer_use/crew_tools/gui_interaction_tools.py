"""
Interactive GUI automation tools for CrewAI.
Refactored for clarity: discovery separate from execution.
"""

from pydantic import BaseModel, Field
from typing import Optional

from .instrumented_tool import InstrumentedBaseTool
from ..schemas.actions import ActionResult
from ..services.state import get_app_state
from ..utils.ui import action_spinner, dashboard, print_action_result
from ..utils.interaction.ocr_targeting import (
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
    app_name: Optional[str] = Field(
        default=None,
        description="Alias for current_app (preferred: current_app).",
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
    allow_cursor_fallback: bool = Field(
        default=False,
        description=(
            "Allow cursor/OCR fallback clicks when accessibility cannot resolve "
            "the element. Defaults to False for accessibility-only interactions."
        ),
    )
    current_app: Optional[str] = Field(
        default=None, description="Current application name"
    )
    explanation: Optional[str] = Field(
        default=None, description="Why this click is needed"
    )


class ClickElementTool(InstrumentedBaseTool):
    """
    Click element using native accessibility or OCR fallback.

    BEST: Pass element_id from get_accessible_elements (native click, 100% accurate)
    FALLBACK: Pass element dict with center coordinates
    LAST RESORT: OCR with visual_context
    """

    name: str = "click_element"
    description: str = """Click element.
    BEST: element_id='<id>' from get_accessible_elements (native click, no duplicates)
    FALLBACK (only if allow_cursor_fallback=True): element=<dict with center>
    LAST (only if allow_cursor_fallback=True): OCR with target and visual_context"""
    args_schema: type[BaseModel] = ClickInput

    def _run(
        self,
        target: Optional[str] = "element",
        app_name: Optional[str] = None,
        element_id: Optional[str] = None,
        element: Optional[dict] = None,
        visual_context: Optional[str] = None,
        click_type: str = "single",
        allow_cursor_fallback: bool = False,
        current_app: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> ActionResult:
        """
        Click element with priority: element_id > element > OCR.

        Args:
            target: Element label (for logging/fallback)
            element_id: Unique ID from get_accessible_elements (best method)
            element: Element dict with 'center' [x, y]
            visual_context: Spatial context for OCR fallback
            click_type: single/double/right
            allow_cursor_fallback: Allow cursor/OCR fallback if accessibility fails
            current_app: Current app name
            explanation: Why this click is needed (for logging)

        Returns:
            ActionResult with click details
        """
        if cancelled := check_cancellation():
            return cancelled

        if app_name and not current_app:
            current_app = app_name
        current_app = get_app_state().get_effective_app(current_app)
        target = target or "element"
        dashboard.set_action("Clicking", target)

        accessibility_tool = self._tool_registry.get_tool("accessibility")
        accessibility_error = None

        if not element_id and element and isinstance(element, dict):
            element_id = element.get("element_id")

        if (
            not element_id
            and accessibility_tool
            and accessibility_tool.available
            and current_app
        ):
            resolved = self._resolve_accessible_element(
                accessibility_tool, current_app, target
            )
            if not resolved:
                resolved = self._resolve_accessible_element_by_ocr(
                    accessibility_tool, current_app, target, visual_context
                )
            if resolved:
                element_id = resolved.get("element_id")
                if not element_id:
                    element_id = resolved.get("id")
                target = resolved.get("label") or target

        if element_id and accessibility_tool and accessibility_tool.available:
            if not element_id.startswith("e_"):
                return ActionResult(
                    success=False,
                    action_taken=f"Invalid element_id '{element_id}'",
                    method_used="accessibility",
                    confidence=0.0,
                    error=f"Invalid element_id '{element_id}'. Use the element_id from get_accessible_elements (starts with 'e_').",
                )
            if hasattr(accessibility_tool, "click_by_id"):
                with action_spinner("Clicking", target):
                    try:
                        success, message = accessibility_tool.click_by_id(
                            element_id, click_type=click_type
                        )
                    except TypeError:
                        success, message = accessibility_tool.click_by_id(element_id)

                print_action_result(success, message)
                if success:
                    return ActionResult(
                        success=success,
                        action_taken=message,
                        method_used="accessibility_native",
                        confidence=1.0,
                        data={"requires_verification": False},
                    )
                accessibility_error = message

        if accessibility_tool and accessibility_tool.available and current_app:
            fallback_reason = (
                f"Accessibility click failed: {accessibility_error}."
                if accessibility_error
                else f"No accessible element matched '{target}'."
            )
            if not allow_cursor_fallback:
                print_action_result(
                    False, "Click failed - call get_accessible_elements() to refresh"
                )
                return ActionResult(
                    success=False,
                    action_taken=f"Failed to click {target}",
                    method_used="accessibility_native",
                    confidence=0.0,
                    error=f"{fallback_reason} Call get_accessible_elements() to refresh element list.",
                    data={"requires_refresh": True},
                )
            print_action_result(
                True, f"{fallback_reason} Falling back to cursor input."
            )

        input_tool = self._tool_registry.get_tool("input")

        if element and allow_cursor_fallback:
            x, y = None, None

            if "center" in element:
                center = element["center"]
                if isinstance(center, list) and len(center) == 2:
                    x, y = center
            elif "x" in element and "y" in element:
                ex, ey = element["x"], element["y"]
                ew = element.get("width", 0)
                eh = element.get("height", 0)
                x = int(ex + ew / 2)
                y = int(ey + eh / 2)

            if x is not None and y is not None:
                with action_spinner("Clicking", target):
                    if click_type == "double":
                        success = input_tool.double_click(x, y, validate=True)
                    elif click_type == "right":
                        success = input_tool.right_click(x, y, validate=True)
                    else:
                        success = input_tool.click(x, y, validate=True)

                print_action_result(success, f"Clicked {target}")

                return ActionResult(
                    success=success,
                    action_taken=f"Clicked {target}",
                    method_used="element_coordinates",
                    confidence=1.0,
                    data={"coordinates": (x, y), "requires_verification": False},
                )

        if not allow_cursor_fallback:
            return ActionResult(
                success=False,
                action_taken=f"Failed to click {target}",
                method_used="accessibility_native",
                confidence=0.0,
                error=(
                    "Accessibility click failed and cursor fallback is disabled. "
                    "Use get_accessible_elements or search_elements to obtain element_id."
                ),
            )

        ocr_warning = (
            f"⚠️ SLOW PATH: Using OCR fallback for '{target}'. "
            "Use element_id from get_accessible_elements for faster native clicks."
        )
        print_action_result(True, ocr_warning)

        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")

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

        print_action_result(success, "Clicked via OCR (SLOW)")

        return ActionResult(
            success=success,
            action_taken=f"Clicked {target} (via OCR - SLOW). Next time use element_id for faster native clicks.",
            method_used="ocr",
            confidence=best_match.confidence,
            data={
                "coordinates": (x_screen, y_screen),
                "matched_text": best_match.text,
                "score": best_score,
                "requires_verification": True,
                "warning": "OCR fallback is slow. Use element_id from get_accessible_elements.",
            },
        )

    def _resolve_accessible_element(
        self, accessibility_tool, current_app: Optional[str], target: str
    ) -> Optional[dict]:
        if not current_app:
            return None

        target_raw = (target or "").strip()
        if not target_raw:
            return None

        try:
            try:
                elements = accessibility_tool.get_elements(
                    current_app, interactive_only=True, use_cache=True
                )
            except TypeError:
                elements = accessibility_tool.get_elements(
                    current_app, interactive_only=True
                )
        except Exception:
            return None

        if not elements:
            return None

        target_variants = self._build_target_variants(target_raw)
        target_lower = target_raw.lower()
        prefer_button = self._prefer_button_role(target_raw)

        best = None
        best_score = -1

        for elem in elements:
            label = (elem.get("label") or "").strip()
            identifier = (elem.get("identifier") or "").strip()
            role = (elem.get("role") or "").strip().lower()

            if prefer_button and "button" not in role:
                continue

            score = self._score_target_match(
                label, identifier, role, target_variants, target_lower
            )
            if score <= 0:
                continue

            if score > best_score:
                best_score = score
                best = elem

        return best

    def _resolve_accessible_element_by_ocr(
        self,
        accessibility_tool,
        current_app: str,
        target: str,
        visual_context: Optional[str] = None,
    ) -> Optional[dict]:
        if (
            not current_app
            or not accessibility_tool
            or not accessibility_tool.available
        ):
            return None

        screenshot_tool = self._tool_registry.get_tool("screenshot")
        ocr_tool = self._tool_registry.get_tool("ocr")

        if not screenshot_tool or not ocr_tool:
            return None

        screenshot = screenshot_tool.capture()
        scaling = getattr(screenshot_tool, "scaling_factor", 1.0)
        ocr_screenshot = screenshot
        x_offset = 0
        y_offset = 0

        window_bounds = None
        if hasattr(accessibility_tool, "get_app_window_bounds"):
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

        target_raw = (target or "").strip()
        if not target_raw:
            return None

        target_variants = self._build_target_variants(target_raw)
        candidates = []

        try:
            for variant in target_variants:
                matches = ocr_tool.find_text(ocr_screenshot, variant, fuzzy=False)
                if matches:
                    candidates.extend(matches)
        except Exception:
            pass

        if not candidates:
            try:
                for variant in target_variants:
                    matches = ocr_tool.find_text(ocr_screenshot, variant, fuzzy=True)
                    if matches:
                        candidates.extend(matches)
            except Exception:
                pass

        if not candidates:
            try:
                candidates = ocr_tool.extract_all_text(ocr_screenshot) or []
            except Exception:
                candidates = []

        if not candidates:
            return None

        if visual_context:
            candidates = filter_candidates_by_spatial_context(
                candidates,
                visual_context,
                ocr_screenshot.width,
                ocr_screenshot.height,
            )

        best_match = None
        best_score = -999.0

        for item in candidates:
            for variant in target_variants:
                score, _ = score_ocr_candidate(
                    item,
                    variant.lower(),
                    ocr_screenshot.width,
                    ocr_screenshot.height,
                    visual_context,
                )
                if score > best_score:
                    best_score = score
                    best_match = item

        if not best_match or best_score < 500.0:
            return None

        x_raw, y_raw = best_match.center
        x_screen = int(x_raw / scaling) + x_offset
        y_screen = int(y_raw / scaling) + y_offset

        try:
            accessibility_tool.invalidate_cache(current_app)
        except Exception:
            pass

        try:
            elements = accessibility_tool.get_elements(
                current_app, interactive_only=True, use_cache=False
            )
        except TypeError:
            elements = accessibility_tool.get_elements(
                current_app, interactive_only=True
            )

        if not elements:
            try:
                elements = accessibility_tool.get_elements(
                    current_app, interactive_only=False, use_cache=False
                )
            except TypeError:
                elements = accessibility_tool.get_elements(
                    current_app, interactive_only=False
                )

        if not elements:
            return None

        return self._pick_element_near_point(
            elements,
            (x_screen, y_screen),
            target_variants,
            target_raw.lower(),
            window_bounds,
        )

    def _pick_element_near_point(
        self,
        elements: list[dict],
        point: tuple[int, int],
        target_variants: list[str],
        target_lower: str,
        window_bounds: Optional[tuple[int, int, int, int]],
    ) -> Optional[dict]:
        import math

        px, py = point
        best = None
        best_score = -1.0

        for elem in elements:
            bounds = elem.get("bounds") or []
            center = elem.get("center") or []
            if len(bounds) != 4 or len(center) != 2:
                continue

            cx, cy = center
            if window_bounds:
                wx, wy, ww, wh = window_bounds
                if not (wx <= cx <= wx + ww and wy <= cy <= wy + wh):
                    continue

            x, y, w, h = bounds
            inside = x <= px <= x + w and y <= py <= y + h
            distance = math.hypot(cx - px, cy - py)

            role = (elem.get("role") or "").strip().lower()
            label = (elem.get("label") or "").strip()
            identifier = (elem.get("identifier") or "").strip()

            score = 0.0
            if inside:
                score += 1000.0
            score += max(0.0, 400.0 - distance)

            if "button" in role:
                score += 50.0
            if "menu" in role:
                score -= 200.0

            if target_variants:
                label_score = self._score_target_match(
                    label, identifier, role, target_variants, target_lower
                )
                if label_score > 0:
                    score += 200.0 + float(label_score)

            if score > best_score:
                best_score = score
                best = elem

        if best_score < 350.0:
            return None

        return best

    def _build_target_variants(self, target: str) -> list[str]:
        variants = [target]
        if target in {"*", "x", "X", "×"}:
            variants.extend(["×", "*", "x", "X"])
        if target in {"/", "÷"}:
            variants.extend(["÷", "/"])
        if target in {"-", "−"}:
            variants.extend(["-", "−"])
        if target == "C":
            variants.extend(["AC", "CE", "Clear", "All Clear", "Clear Entry"])
        if target == ".":
            variants.append(".")
        return list(dict.fromkeys(v for v in variants if v))

    def _prefer_button_role(self, target: str) -> bool:
        target_lower = target.strip().lower()
        if target_lower.isdigit():
            return True
        if target_lower in {
            "=",
            "+",
            "-",
            "×",
            "÷",
            "*",
            "/",
            "%",
            ".",
            "c",
            "ac",
            "ce",
        }:
            return True
        return len(target_lower) <= 2

    def _score_target_match(
        self,
        label: str,
        identifier: str,
        role: str,
        variants: list[str],
        target_lower: str,
    ) -> int:
        label_lower = label.lower()
        identifier_lower = identifier.lower()
        score = 0

        for variant in variants:
            variant_lower = variant.lower()
            if label_lower == variant_lower:
                score = max(score, 100)
            elif identifier_lower == variant_lower:
                score = max(score, 95)
            elif len(variant_lower) > 2 and variant_lower in label_lower:
                score = max(score, 60)
            elif len(variant_lower) > 2 and variant_lower in identifier_lower:
                score = max(score, 50)

        if score == 0:
            return 0

        if "button" in role:
            score += 10
        if "menu" in role:
            score -= 5
        if label_lower == target_lower:
            score += 5

        return score


class TypeInput(BaseModel):
    """Input for typing text."""

    text: str = Field(description="Text to type")
    use_clipboard: bool = Field(default=False, description="Force clipboard paste")
    explanation: Optional[str] = Field(
        default=None, description="Why this text is being typed"
    )
    require_app: Optional[str] = Field(
        default=None,
        description=(
            "For keyboard shortcuts: app that MUST be focused before sending. "
            "If specified and app is not focused, action will be BLOCKED. "
            "Example: require_app='Finder' for cmd+shift+g."
        ),
    )


class TypeTextTool(InstrumentedBaseTool):
    """Type text with smart paste detection, hotkey support, and app focus validation."""

    name: str = "type_text"
    description: str = """Type text, numbers, or keyboard shortcuts.
    IMPORTANT: To type into a text field, you MUST click the field first with click_element to focus it.
    Text goes to whatever UI element currently has keyboard focus.
    Smart paste for paths, URLs, long text. Supports hotkeys (cmd+c, ctrl+v).
    For hotkeys: use require_app to ensure correct app is focused before sending.
    To press Enter/Return key: use text="\\n" (NOT "enter" which types literal text)."""
    args_schema: type[BaseModel] = TypeInput

    def _run(
        self,
        text: str,
        use_clipboard: bool = False,
        explanation: Optional[str] = None,
        require_app: Optional[str] = None,
    ) -> ActionResult:
        """
        Type text with smart paste detection and optional app focus validation.

        Args:
            text: Text to type
            use_clipboard: Force paste
            explanation: Why this text is being typed (for logging)
            require_app: App that must be focused for hotkeys (BLOCKS if not focused)

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

        hotkey_sequences: list[list[str]] = []
        if "+" in text:
            candidates = [c.strip() for c in text.split(",") if c.strip()]
            for candidate in candidates:
                if "+" not in candidate:
                    hotkey_sequences = []
                    break
                parts = [p.strip().lower() for p in candidate.split("+") if p.strip()]
                if not (2 <= len(parts) <= 4):
                    hotkey_sequences = []
                    break

                key_map = {
                    "cmd": "command",
                    "ctrl": "ctrl",
                    "alt": "alt",
                    "shift": "shift",
                }
                hotkey_sequences.append([key_map.get(k, k) for k in parts])

        is_hotkey = len(hotkey_sequences) > 0

        if is_hotkey and require_app:
            from ..services.state import StateObserver

            observer = StateObserver(self._tool_registry)
            is_focused, message = observer.verify_precondition(
                "app_focused", app_name=require_app
            )

            if not is_focused:
                state = observer.capture_state()
                return ActionResult(
                    success=False,
                    action_taken=f"BLOCKED: Hotkey '{text}' requires {require_app} to be focused",
                    method_used="precondition_check",
                    confidence=0.0,
                    error=(
                        f"Precondition failed: {message}. "
                        f"ACTION REQUIRED: Call open_application('{require_app}') first to focus it."
                    ),
                    data={
                        "blocked_reason": "app_not_focused",
                        "required_app": require_app,
                        "current_frontmost": state.active_app,
                    },
                )

        display_text = text[:20] + "..." if len(text) > 20 else text
        dashboard.set_action("Typing", display_text)

        input_tool = self._tool_registry.get_tool("input")

        try:
            if is_hotkey:
                import time

                timing = get_timing_config()
                for keys in hotkey_sequences:
                    input_tool.hotkey(*keys)
                    time.sleep(timing.ui_state_change_delay)
                return ActionResult(
                    success=True,
                    action_taken=f"Pressed hotkey: {text}",
                    method_used="type",
                    confidence=1.0,
                )

            elif text == "\\n" or text == "\n":
                import pyautogui

                pyautogui.press("return")
                return ActionResult(
                    success=True,
                    action_taken="Pressed Enter",
                    method_used="type",
                    confidence=1.0,
                )

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
