"""
Basic GUI automation tools for CrewAI.
Simple tools: screenshot, open_application, read_screen, scroll.
"""

import atexit
import os
from pydantic import BaseModel, Field
from typing import Optional, Set

from .instrumented_tool import InstrumentedBaseTool
from ..schemas.actions import ActionResult
from ..config.timing_config import get_timing_config
from ..services.state import get_app_state
from ..utils.ui import ActionType, action_spinner, dashboard, print_action_result


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


class TakeScreenshotTool(InstrumentedBaseTool):
    """Capture screenshot of screen or region."""

    name: str = "take_screenshot"
    description: str = "Capture screenshot of screen or app window."
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
    explanation: Optional[str] = Field(
        default=None, description="Why this app is being opened"
    )


class OpenApplicationTool(InstrumentedBaseTool):
    """Open desktop application."""

    name: str = "open_application"
    description: str = "Open desktop application by name (e.g., Calculator, Notes)"
    args_schema: type[BaseModel] = OpenAppInput

    def _wait_for_app_ready(
        self, app_name: str, timeout: float = 5.0, poll_interval: float = 0.2
    ) -> bool:
        """
        Wait for app to be ready by checking for accessible windows.

        Args:
            app_name: Application name
            timeout: Max seconds to wait (default 5)
            poll_interval: Seconds between checks (default 0.2)

        Returns:
            True if app has windows, False if timeout reached
        """
        import time

        accessibility = self._tool_registry.get_tool("accessibility")
        if not accessibility or not accessibility.available:
            time.sleep(1.0)
            return True

        accessibility.invalidate_cache(app_name)

        start = time.time()
        while (time.time() - start) < timeout:
            try:
                app_ref = accessibility.get_app(app_name, retry_count=1)
                if app_ref:
                    windows = accessibility.get_windows(app_ref)
                    if windows and len(windows) > 0:
                        return True
            except Exception:
                pass
            time.sleep(poll_interval)
            accessibility.invalidate_cache(app_name)

        return False

    def _run(self, app_name: str, explanation: Optional[str] = None) -> ActionResult:
        """
        Open application without blocking for frontmost status.

        Accessibility API clicks work WITHOUT the app being frontmost.
        Only coordinate-based clicks (pyautogui) require frontmost.
        This tool now returns success as soon as the app is running.

        Args:
            app_name: Application name
            explanation: Why this app is being opened (for logging)

        Returns:
            ActionResult with launch details
        """
        if cancelled := check_cancellation():
            return cancelled

        process_tool = self._tool_registry.get_tool("process")

        try:
            with action_spinner("Opening", app_name):
                result = process_tool.open_application(app_name)

            if not result.get("success", False):
                print_action_result(False, f"Failed to launch {app_name}")
                return ActionResult(
                    success=False,
                    action_taken=f"Failed to launch {app_name}",
                    method_used="process",
                    confidence=0.0,
                    error=result.get("message", "Launch failed"),
                )

            get_app_state().set_target_app(app_name)

            try:
                process_tool.focus_app(app_name)
            except Exception:
                pass

            app_ready = self._wait_for_app_ready(app_name, timeout=5.0)

            if app_ready:
                print_action_result(True, f"Opened {app_name}")
                return ActionResult(
                    success=True,
                    action_taken=f"Opened {app_name} (ready)",
                    method_used="process",
                    confidence=1.0,
                    data={"is_running": True, "has_windows": True},
                )
            else:
                print_action_result(True, f"Opened {app_name} (no windows yet)")
                return ActionResult(
                    success=True,
                    action_taken=f"Opened {app_name} (may still be loading)",
                    method_used="process",
                    confidence=0.7,
                    data={"is_running": True, "has_windows": False},
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


class ReadScreenTextTool(InstrumentedBaseTool):
    """Extract text from screen using OCR."""

    name: str = "read_screen_text"
    description: str = "Extract text from screen or app window via OCR."
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
        if cancelled := check_cancellation():
            return cancelled

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

            from ..utils.ui.core.responsive import ResponsiveWidth

            text_preview = ResponsiveWidth.truncate(
                full_text, max_ratio=0.8, min_width=60
            )
            source = f"{app_name} window" if app_name else "screen"

            return ActionResult(
                success=True,
                action_taken=f"Read text from {source}: {text_preview}",
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


class ScrollTool(InstrumentedBaseTool):
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
            with action_spinner("Scrolling", direction):
                if direction == "down":
                    input_tool.scroll(-amount)
                else:
                    input_tool.scroll(amount)

            print_action_result(True, f"Scrolled {direction}")
            return ActionResult(
                success=True,
                action_taken=f"Scrolled {direction}",
                method_used="scroll",
                confidence=1.0,
                data={"direction": direction},
            )
        except Exception as e:
            print_action_result(False, f"Scroll failed: {e}")
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


class ListRunningAppsTool(InstrumentedBaseTool):
    """List all currently running applications."""

    name: str = "list_running_apps"
    description: str = "List all currently running applications."
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
                unique_apps = sorted(set(running_apps))
                visible_apps = [
                    a
                    for a in unique_apps
                    if not any(
                        x in a.lower()
                        for x in ["helper", "agent", "service", "extension", "server"]
                    )
                ]
                top_visible = visible_apps[:10]
                apps_summary = ", ".join(top_visible)
                if len(visible_apps) > len(top_visible):
                    apps_summary += f" … +{len(visible_apps) - len(top_visible)} more"

                return ActionResult(
                    success=True,
                    action_taken=f"Found {len(unique_apps)} apps. User-facing (sample): {apps_summary}",
                    method_used="accessibility",
                    confidence=1.0,
                    data={
                        "running_apps": unique_apps,
                        "count": len(unique_apps),
                        "visible_sample": top_visible,
                    },
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


class CheckAppRunningTool(InstrumentedBaseTool):
    """Check if a specific application is currently running."""

    name: str = "check_app_running"
    description: str = "Check if an app is running."
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

            status = "RUNNING" if is_running else "NOT RUNNING"
            return ActionResult(
                success=True,
                action_taken=f"{app_name} is {status}",
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

    app_name: Optional[str] = Field(
        default=None,
        description="Application name to get elements from. If not provided, uses current target app.",
    )
    filter_text: Optional[str] = Field(
        default=None,
        description="Optional text to filter elements by (case-insensitive search in label/title)",
    )
    filter_role: Optional[str] = Field(
        default=None,
        description="Filter by element role/type (TextField, TextArea, Button, CheckBox, MenuItem, etc.)",
    )


_get_elements_state = {"last_hash": "", "repeat_count": 0}

INPUT_PRIORITY_ROLES = frozenset(
    {
        "textfield",
        "textarea",
        "searchfield",
        "combobox",
        "securetextfield",
        "edit",
        "text",
        "entry",
    }
)
"""
INPUT_PRIORITY_ROLES: Roles used for DISPLAY SORTING only.

These roles are NOT used for filtering elements from the accessibility API.
All elements returned by the accessibility API are included regardless of role.
This set only affects display order: input fields are shown first to the LLM
since they're commonly needed for interaction (typing, form filling).
"""


def _get_element_priority(element: dict) -> tuple:
    """Get sort priority for element - input fields first, then by position."""
    role = (element.get("role") or "").lower()
    center = element.get("center", [9999, 9999])
    is_input = 0 if role in INPUT_PRIORITY_ROLES else 1
    return (is_input, center[1] if center else 9999, center[0] if center else 9999)


def _format_elements_brief(elements: list) -> str:
    """
    Format elements as a compact role count summary.

    Args:
        elements: List of element dictionaries

    Returns:
        Compact summary such as: "Button:56 | MenuItem:12 | TextField:2 | +3 more"
    """
    from typing import Dict

    by_role: Dict[str, int] = {}
    for e in elements:
        role = e.get("role", "Other") or "Other"
        by_role[role] = by_role.get(role, 0) + 1

    top = sorted(by_role.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    parts = [f"{role}:{count}" for role, count in top]
    if len(by_role) > len(top):
        parts.append(f"+{len(by_role) - len(top)} more")
    return " | ".join(parts)


def _is_meaningful_label(label: str) -> bool:
    """
    Determine whether an element label is meaningful for LLM selection.

    Args:
        label: Raw label string

    Returns:
        True if label is non-empty and not a generic placeholder
    """
    if not label:
        return False
    cleaned = label.strip()
    if not cleaned:
        return False
    if cleaned.lower() in {"button", "group", "toolbar", "menu"}:
        return False
    if cleaned.startswith("[") and cleaned.endswith("]"):
        return False
    return True


def _should_apply_ocr_labels(
    elements: list[dict], filter_text: Optional[str], filter_role: Optional[str]
) -> bool:
    if filter_text or filter_role:
        return True

    button_total = 0
    button_labeled = 0
    for e in elements:
        role = (e.get("role") or "").lower()
        if "button" not in role:
            continue
        button_total += 1
        if _is_meaningful_label(e.get("label", "")):
            button_labeled += 1

    if button_total >= 10 and button_labeled < max(3, int(button_total * 0.2)):
        return True
    return False


def _apply_ocr_labels(
    elements: list[dict],
    app_name: str,
    accessibility_tool,
    tool_registry,
    filter_text: Optional[str],
    filter_role: Optional[str],
) -> None:
    if not _should_apply_ocr_labels(elements, filter_text, filter_role):
        return

    screenshot_tool = tool_registry.get_tool("screenshot")
    ocr_tool = tool_registry.get_tool("ocr")

    if not screenshot_tool or not ocr_tool:
        return

    window_bounds = None
    if accessibility_tool and hasattr(accessibility_tool, "get_app_window_bounds"):
        window_bounds = accessibility_tool.get_app_window_bounds(app_name)

    screenshot = screenshot_tool.capture()
    scaling = getattr(screenshot_tool, "scaling_factor", 1.0)
    ocr_screenshot = screenshot
    x_offset = 0
    y_offset = 0

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

    try:
        ocr_items = ocr_tool.extract_all_text(ocr_screenshot) or []
    except Exception:
        return

    if not ocr_items:
        return

    screen_items = []
    for item in ocr_items:
        text = (item.text or "").strip()
        if not text:
            continue
        x_raw, y_raw = item.center
        x_screen = int(x_raw / scaling) + x_offset
        y_screen = int(y_raw / scaling) + y_offset
        screen_items.append(
            {
                "text": text,
                "center": (x_screen, y_screen),
                "confidence": float(item.confidence or 0.0),
            }
        )

    if not screen_items:
        return

    for elem in elements:
        label = (elem.get("label") or "").strip()
        if _is_meaningful_label(label):
            continue

        bounds = elem.get("bounds") or []
        if len(bounds) != 4:
            continue

        x, y, w, h = bounds
        best_text = None
        best_conf = -1.0
        best_len = 9999

        for item in screen_items:
            cx, cy = item["center"]
            if not (x <= cx <= x + w and y <= cy <= y + h):
                continue
            text = item["text"]
            conf = item["confidence"]
            text_len = len(text)
            if conf > best_conf or (conf == best_conf and text_len < best_len):
                best_text = text
                best_conf = conf
                best_len = text_len

        if best_text:
            elem["label"] = best_text
            elem["title"] = best_text


def _format_label_id(label: str, element_id: str, max_len: int = 22) -> str:
    """
    Format a label with element_id in a compact, readable form.

    Args:
        label: Element label
        element_id: Element ID string
        max_len: Maximum label length before truncation

    Returns:
        Formatted string like: "Save(e_1234567)"
    """
    lbl = (label or "").strip()
    if len(lbl) > max_len:
        lbl = lbl[: max_len - 1].rstrip() + "…"
    return f"{lbl}({element_id})"


def _select_smart_compact_elements(
    elements: list, max_total: int = 20
) -> tuple[list[dict], int]:
    """
    Select a small, high-signal subset of elements for LLM display.

    Uses single-pass bucketing for O(n) performance instead of O(n² log n).

    Strategy:
    - ALWAYS include ALL input fields (TextField, TextArea) - these are critical
    - Then include labeled interactive elements by role priority
    - Prefer unique labels and top-to-bottom layout ordering

    Args:
        elements: Full list of interactive elements
        max_total: Maximum number of elements to select

    Returns:
        (selected_elements, hidden_count)
    """
    from collections import defaultdict

    if max_total <= 0:
        return ([], len(elements))

    by_role: dict[str, list[dict]] = defaultdict(list)
    input_elements: list[dict] = []
    label_counts: dict[str, int] = {}

    for e in elements:
        role = e.get("role") or ""
        role_lower = role.lower()
        label = (e.get("label") or "").strip()

        if _is_meaningful_label(label):
            label_counts[label] = label_counts.get(label, 0) + 1
            by_role[role].append(e)

        if role_lower in INPUT_PRIORITY_ROLES:
            input_elements.append(e)

    def score(e: dict) -> tuple:
        label = (e.get("label") or "").strip()
        role = (e.get("role") or "").lower()
        unique = 0 if label_counts.get(label, 0) == 1 else 1
        is_list_item = role in ("group", "cell", "row")
        length = (
            -len(label) if (is_list_item and label) else (len(label) if label else 999)
        )
        center = e.get("center") or [9999, 9999]
        return (unique, length, center[1], center[0])

    input_elements.sort(key=_get_element_priority)

    selected: list[dict] = []
    seen_ids: set[str] = set()

    for e in input_elements:
        eid = e.get("element_id") or ""
        if eid and eid not in seen_ids:
            selected.append(e)
            seen_ids.add(eid)

    remaining_slots = max(0, max_total - len(selected))

    role_priority = [
        ("Button", 12),
        ("Group", 15),
        ("Cell", 10),
        ("Row", 10),
        ("MenuItem", 8),
        ("MenuBarItem", 4),
        ("CheckBox", 4),
        ("RadioButton", 4),
        ("MenuButton", 2),
        ("PopUpButton", 2),
        ("StaticText", 6),
    ]

    for role, per_role_cap in role_priority:
        if remaining_slots <= 0:
            break
        candidates = by_role.get(role, [])
        if not candidates:
            continue
        take = min(remaining_slots, per_role_cap)
        candidates.sort(key=score)
        for e in candidates[:take]:
            if remaining_slots <= 0:
                break
            eid = e.get("element_id") or ""
            if eid and eid not in seen_ids:
                selected.append(e)
                seen_ids.add(eid)
                remaining_slots -= 1

    hidden = max(0, len(elements) - len(selected))
    return (selected, hidden)


def _format_elements_smart_compact(selected: list[dict], hidden_count: int) -> str:
    """
    Format a smart-compact list of elements for minimal token usage.

    Separates INPUT FIELDS (where you type) from other UI elements for clarity.

    Args:
        selected: Selected elements to display
        hidden_count: Count of additional elements not shown

    Returns:
        Multi-line formatted summary with input fields prominently displayed
    """
    input_fields: list[str] = []
    by_role: dict[str, list[str]] = {}

    for e in selected:
        role = e.get("role") or "Other"
        label = (e.get("label") or "").strip()
        eid = e.get("element_id") or ""
        if not eid:
            continue

        role_lower = role.lower()
        is_input_role = role_lower in INPUT_PRIORITY_ROLES
        is_focused = e.get("focused", False)
        is_bottom = e.get("is_bottom", False)

        focus_marker = "→" if is_focused else ""
        pos_hint = "[bottom]" if is_bottom and is_input_role else ""

        if is_input_role and role_lower in (
            "textfield",
            "securetextfield",
            "searchfield",
            "combobox",
        ):
            if label:
                display = f"{focus_marker}{label}{pos_hint}({eid})"
            else:
                display = f"{focus_marker}[unlabeled]{pos_hint}({eid})"
            input_fields.append(f"{role}: {display.strip()}")
        elif is_input_role and role_lower == "textarea":
            label_preview = label[:30] + "…" if len(label) > 30 else label
            label_lower = label.lower()
            is_placeholder = label_lower in (
                "",
                "message",
                "imessage",
                "type a message",
                "text message",
            )
            is_empty_or_placeholder = is_placeholder or not label
            is_likely_input = is_focused or is_empty_or_placeholder
            if is_likely_input:
                display = f"{focus_marker}{label_preview or '[empty]'}{pos_hint}({eid})"
                input_fields.append(f"TextArea(input): {display.strip()}")
        else:
            if label:
                by_role.setdefault(role, []).append(_format_label_id(label, eid))
            else:
                by_role.setdefault(role, []).append(
                    _format_label_id("[unlabeled]", eid)
                )

    role_order = [
        "Button",
        "Group",
        "Cell",
        "Row",
        "MenuItem",
        "MenuBarItem",
        "CheckBox",
        "RadioButton",
        "MenuButton",
        "PopUpButton",
        "StaticText",
    ]

    lines: list[str] = []

    if input_fields:
        lines.append("═══ INPUT FIELDS (click then type) ═══")
        lines.extend(input_fields)
        lines.append("")

    for role in role_order:
        items = by_role.pop(role, [])
        if items:
            lines.append(f"{role}: " + ", ".join(items))

    for role, items in sorted(by_role.items()):
        if items:
            lines.append(f"{role}: " + ", ".join(items))

    if hidden_count > 0:
        lines.append(
            f"+{hidden_count} more elements hidden (use filter_text / filter_role)"
        )

    return "\n".join(lines) if lines else "No actionable labeled elements found"


class GetAccessibleElementsTool(InstrumentedBaseTool):
    """
    Get all interactive elements from an application using Accessibility API.
    Returns a structured list of clickable elements with their coordinates.
    """

    name: str = "get_accessible_elements"
    description: str = (
        "Get UI elements from app. Returns element IDs for click_element."
    )
    args_schema: type[BaseModel] = GetAccessibleElementsInput

    def _run(
        self,
        app_name: Optional[str] = None,
        filter_text: Optional[str] = None,
        filter_role: Optional[str] = None,
    ) -> ActionResult:
        """
        Get all accessible elements from app using comprehensive UI element detection.

        Args:
            app_name: Application name (optional, uses current target if not provided)
            filter_text: Optional text to filter elements by label/title
            filter_role: Optional role/type to filter elements by (TextField, Button, etc.)

        Returns:
            ActionResult with categorized list of elements
        """
        if cancelled := check_cancellation():
            return cancelled

        effective_app = get_app_state().get_effective_app(app_name)
        if not effective_app:
            return ActionResult(
                success=False,
                action_taken="No application specified",
                method_used="accessibility",
                confidence=0.0,
                error="No app_name provided and no target app set. Call open_application first or specify app_name.",
            )
        app_name = effective_app

        if not hasattr(self, "_tool_registry") or self._tool_registry is None:
            return ActionResult(
                success=False,
                action_taken=f"Tool registry not initialized for {app_name}",
                method_used="accessibility",
                confidence=0.0,
                error="Internal error: _tool_registry not set on tool instance",
            )

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
            dashboard.set_action("Scanning", f"{app_name} UI")
            import time

            timing = get_timing_config()
            retry_count = max(1, timing.accessibility_retry_count)
            elements = []
            app_ref = None
            windows = []
            with action_spinner("Scanning", f"{app_name} UI"):
                for attempt in range(retry_count):
                    if attempt == 0:
                        accessibility_tool.invalidate_cache(app_name)

                    use_cache = attempt == 0
                    elements = accessibility_tool.get_elements(
                        app_name, interactive_only=True, use_cache=use_cache
                    )
                    if elements:
                        break

                    app_ref = accessibility_tool.get_app(app_name, retry_count=1)
                    windows = accessibility_tool.get_windows(app_ref) if app_ref else []

                    if windows:
                        time.sleep(timing.accessibility_api_delay)
                    else:
                        time.sleep(timing.app_launch_retry_interval)

                    accessibility_tool.invalidate_cache(app_name)

            if not elements:
                if app_ref is None:
                    app_ref = accessibility_tool.get_app(app_name, retry_count=1)
                window_info = []
                if app_ref:
                    windows = accessibility_tool.get_windows(app_ref)
                    for w in windows[:3]:
                        try:
                            title = getattr(w, "AXTitle", None) or "untitled"
                            role = getattr(w, "AXRole", None) or "unknown"
                            window_info.append(f"{role}:{title}")
                        except Exception:
                            window_info.append("error")

                debug_info = (
                    f"app_found={app_ref is not None}, "
                    f"windows={len(windows)}, "
                    f"window_details={window_info}"
                )

                if len(windows) == 0:
                    process_tool = self._tool_registry.get_tool("process")
                    if process_tool:
                        process_tool.focus_app(app_name)
                        time.sleep(timing.app_focus_delay)
                        accessibility_tool.invalidate_cache(app_name)
                        elements = accessibility_tool.get_elements(
                            app_name, interactive_only=True, use_cache=False
                        )
                    if not elements:
                        return ActionResult(
                            success=False,
                            action_taken=f"{app_name} has no visible windows. The app may be minimized or not fully launched.",
                            method_used="accessibility",
                            confidence=0.0,
                            error=f"No windows found for {app_name}. Try clicking on the app or using open_application first.",
                            data={
                                "elements": [],
                                "count": 0,
                                "debug": debug_info,
                                "windows": 0,
                            },
                        )

                if not elements:
                    return ActionResult(
                        success=True,
                        action_taken=f"No interactive elements found in {app_name}. Debug: {debug_info}. The app window exists but contains no clickable UI elements. Try using get_window_image to see screen state.",
                        method_used="accessibility",
                        confidence=0.5,
                        data={"elements": [], "count": 0, "debug": debug_info},
                    )

            print_action_result(True, f"Found {len(elements)} elements")

            window_bounds = None
            if hasattr(accessibility_tool, "get_app_window_bounds"):
                window_bounds = accessibility_tool.get_app_window_bounds(app_name)

            timing = get_timing_config()
            window_y_start = window_bounds[1] if window_bounds else 0
            window_height = (
                window_bounds[3] if window_bounds else timing.default_window_height
            )
            _ = (window_y_start, window_height)

            normalized_elements = []
            for elem in elements:
                bounds = list(elem.get("bounds", []))
                center = list(elem.get("center", []))

                label = elem.get("label", "") or elem.get("role", "")
                title = elem.get("title", "") or elem.get("role", "")

                normalized = {
                    "element_id": elem.get("element_id", ""),
                    "label": label,
                    "title": title,
                    "role": elem.get("role", ""),
                    "identifier": elem.get("identifier", ""),
                    "bounds": bounds,
                    "center": center,
                    "category": elem.get("category", "interactive"),
                    "focused": elem.get("focused", False),
                    "is_bottom": elem.get("is_bottom", False),
                }
                normalized_elements.append(normalized)

            normalized_elements.sort(key=_get_element_priority)

            _apply_ocr_labels(
                normalized_elements,
                app_name,
                accessibility_tool,
                self._tool_registry,
                filter_text,
                filter_role,
            )

            if filter_role:
                role_lower = filter_role.lower()
                normalized_elements = [
                    e
                    for e in normalized_elements
                    if role_lower in (e.get("role", "") or "").lower()
                ]
                if not normalized_elements:
                    return ActionResult(
                        success=True,
                        action_taken=f"No elements with role '{filter_role}' found in {app_name}",
                        method_used="accessibility",
                        confidence=1.0,
                        data={"elements": [], "count": 0, "filter_role": filter_role},
                    )

            if filter_text:
                filter_lower = filter_text.lower()
                normalized_elements = [
                    e
                    for e in normalized_elements
                    if filter_lower in (e.get("label", "") or "").lower()
                    or filter_lower in (e.get("title", "") or "").lower()
                ]
                if not normalized_elements:
                    return ActionResult(
                        success=True,
                        action_taken=f"No elements matching '{filter_text}' found in {app_name}",
                        method_used="accessibility",
                        confidence=1.0,
                        data={"elements": [], "count": 0, "filter": filter_text},
                    )

            if filter_text or filter_role:
                max_total = 200
                selected = normalized_elements[:max_total]
                hidden_count = max(0, len(normalized_elements) - len(selected))
            else:
                if len(normalized_elements) <= 80:
                    selected = normalized_elements
                    hidden_count = 0
                else:
                    max_total = 30
                    selected, hidden_count = _select_smart_compact_elements(
                        normalized_elements, max_total=max_total
                    )
            elements_summary = _format_elements_smart_compact(selected, hidden_count)

            import hashlib

            current_hash = hashlib.md5(elements_summary.encode()).hexdigest()[:8]
            ui_changed_msg = ""

            if current_hash == _get_elements_state["last_hash"]:
                _get_elements_state["repeat_count"] += 1
                if _get_elements_state["repeat_count"] >= 2:
                    ui_changed_msg = (
                        "\n\nWARNING: UI unchanged! Elements are the same as before. "
                        "Your previous action likely FAILED. Try: scroll first, click a different element, "
                        "or use take_screenshot to see the actual state."
                    )
            else:
                _get_elements_state["repeat_count"] = 0
                ui_changed_msg = "\n\nUI changed - new elements detected."

            _get_elements_state["last_hash"] = current_hash

            brief_summary = _format_elements_brief(normalized_elements)

            data_elements = []
            for e in selected:
                data_elements.append(
                    {
                        "element_id": e.get("element_id", ""),
                        "identifier": e.get("identifier", ""),
                        "role": e.get("role", ""),
                        "label": e.get("label", ""),
                        "title": e.get("title", ""),
                        "center": e.get("center", []),
                    }
                )

            return ActionResult(
                success=True,
                action_taken=(
                    f"Found {len(normalized_elements)} elements in {app_name}: "
                    f"{brief_summary}{ui_changed_msg}\n\n{elements_summary}"
                ),
                method_used="accessibility",
                confidence=1.0,
                data={
                    "elements": data_elements,
                    "returned_count": len(data_elements),
                    "total_count": len(normalized_elements),
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


class GetWindowImageTool(InstrumentedBaseTool):
    """
    Get window image as base64 for vision analysis (on-demand, cost-aware).
    Only call this when OCR and accessibility are insufficient.
    """

    name: str = "get_window_image"
    description: str = "Capture window screenshot for vision analysis."
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
            if element and "bounds" in element and len(element["bounds"]) == 4:
                x, y, w, h = element["bounds"]
                region_tuple = (x, y, w, h)
                image = screenshot_tool.capture(region=region_tuple)
            elif app_name:
                image, _ = screenshot_tool.capture_active_window(app_name)
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

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".png", delete=False
            ) as tmp:
                image.save(tmp, format="PNG")
                temp_path = tmp.name

            TempFileRegistry.register(temp_path)

            return ActionResult(
                success=True,
                action_taken=f"Screenshot saved: {temp_path}",
                method_used="screenshot",
                confidence=1.0,
                data={
                    "path": temp_path,
                    "size": list(image.size),
                    "app_name": app_name,
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


class RequestHumanInputTool(InstrumentedBaseTool):
    """Request human input for ambiguous decisions or dialog choices."""

    name: str = "request_human_input"
    description: str = "Ask user when facing ambiguous dialogs or decisions."
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
        from rich import box
        from rich.panel import Panel
        from rich.text import Text

        from ..utils.ui import THEME, console

        if dashboard.get_current_agent_name() == "Manager":
            dashboard.set_agent("GUI Agent")
            dashboard.set_thinking(f"Requesting human input: {question[:60]}...")

        was_running = dashboard._is_running
        if was_running:
            dashboard.stop_dashboard()

        dashboard.add_log_entry(
            ActionType.ANALYZE,
            "Requesting human input",
            question[:30],
            status="pending",
        )

        panel_content = Text()
        panel_content.append("Context: ", style=f"bold {THEME['muted']}")
        panel_content.append(f"{context}\n\n", style=THEME["fg"])
        panel_content.append("Question: ", style=f"bold {THEME['warning']}")
        panel_content.append(f"{question}\n\n", style=THEME["fg"])
        panel_content.append("Type your response below:", style=THEME["muted"])

        console.print()
        console.print(
            Panel(
                panel_content,
                title=f"[{THEME['warning']}]Input Required[/]",
                border_style=THEME["warning"],
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        try:
            import sys

            sys.stdout.flush()
            sys.stderr.flush()

            user_response = console.input(f"[bold {THEME['primary']}]> [/]").strip()

            if not user_response:
                console.print(f"  [{THEME['warning']}]Empty response - cancelled[/]")
                return ActionResult(
                    success=False,
                    action_taken="Requested human input",
                    method_used="human_input",
                    confidence=0.0,
                    error="User provided empty response",
                )

            console.print(f"  [{THEME['success']}]Received: {user_response}[/]\n")

            if was_running:
                dashboard.start_dashboard()

            return ActionResult(
                success=True,
                action_taken=f"Received human input: {user_response}",
                method_used="human_input",
                confidence=1.0,
                data={"question": question, "response": user_response},
            )

        except (KeyboardInterrupt, EOFError) as e:
            console.print(f"\n  [{THEME['warning']}]Input cancelled: {e}[/]")
            return ActionResult(
                success=False,
                action_taken="User cancelled input request",
                method_used="human_input",
                confidence=0.0,
                error="User cancelled the task",
            )


class SearchElementsInput(BaseModel):
    """Input for searching elements."""

    query: str = Field(
        description="Search query to find elements by label (partial match)"
    )
    app_name: Optional[str] = Field(
        default=None,
        description="Application name. If not provided, uses current target app.",
    )
    role_filter: Optional[str] = Field(
        default=None,
        description="Filter by element role (Button, TextField, MenuItem, etc.)",
    )
    max_results: int = Field(
        default=20,
        description="Maximum number of results to return",
    )


class SearchElementsTool(InstrumentedBaseTool):
    """
    Search for elements beyond the top 30 displayed by get_accessible_elements.

    Use this tool when you need to find a specific element that wasn't in the
    initial list, or when you need to search for elements by partial label.
    """

    name: str = "search_elements"
    description: str = (
        "Search for UI elements by label. Use when element not in top 30."
    )
    args_schema: type[BaseModel] = SearchElementsInput

    def _run(
        self,
        query: str,
        app_name: Optional[str] = None,
        role_filter: Optional[str] = None,
        max_results: int = 20,
    ) -> ActionResult:
        """
        Search for elements matching a query.

        Args:
            query: Search query (partial match on label)
            app_name: Application name (optional, uses current target)
            role_filter: Optional role filter
            max_results: Maximum results to return

        Returns:
            ActionResult with matching elements
        """
        if cancelled := check_cancellation():
            return cancelled

        effective_app = get_app_state().get_effective_app(app_name)
        if not effective_app:
            return ActionResult(
                success=False,
                action_taken="No application specified",
                method_used="search_elements",
                confidence=0.0,
                error="No app_name provided and no target app set.",
            )

        accessibility_tool = self._tool_registry.get_tool("accessibility")

        if not accessibility_tool or not accessibility_tool.available:
            return ActionResult(
                success=False,
                action_taken="Accessibility not available",
                method_used="search_elements",
                confidence=0.0,
                error="Accessibility API unavailable",
            )

        try:
            elements = accessibility_tool.get_elements(
                effective_app, interactive_only=True, use_cache=True
            )

            if not elements:
                return ActionResult(
                    success=True,
                    action_taken=f"No elements found in {effective_app}",
                    method_used="search_elements",
                    confidence=1.0,
                    data={"results": [], "count": 0},
                )

            from ..services.element_index import index_elements, search_elements

            index_elements(elements)
            results = search_elements(query, role_filter, max_results)

            if not results:
                return ActionResult(
                    success=True,
                    action_taken=f"No elements matching '{query}' found in {effective_app}",
                    method_used="search_elements",
                    confidence=1.0,
                    data={"results": [], "count": 0, "total_indexed": len(elements)},
                )

            result_list = []
            output_lines = [f"Found {len(results)} elements matching '{query}':\n"]

            for r in results:
                result_list.append(
                    {
                        "element_id": r.element_id,
                        "label": r.label,
                        "role": r.role,
                        "score": r.match_score,
                    }
                )
                output_lines.append(f"  {r.role}: {r.label[:40]}({r.element_id})")

            return ActionResult(
                success=True,
                action_taken="\n".join(output_lines),
                method_used="search_elements",
                confidence=1.0,
                data={
                    "results": result_list,
                    "count": len(results),
                    "total_indexed": len(elements),
                },
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken=f"Search failed in {effective_app}",
                method_used="search_elements",
                confidence=0.0,
                error=str(e),
            )
