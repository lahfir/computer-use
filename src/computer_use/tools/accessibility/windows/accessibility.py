"""
Windows UI Automation API using pywinauto for fast, accurate element interaction.

Design principles:
- Let the API tell us what's interactive (is_enabled, control_type)
- Integrate with shared registry for stable element IDs
- Use platform normalizer for all role/element conversions
- Consistent API with macOS/Linux implementations
"""

from typing import List, Optional, Dict, Any, Tuple
import platform

from ..protocol import AccessibilityProtocol
from ..element_registry import VersionedElementRegistry
from ..cache_manager import AccessibilityCacheManager
from .role_normalizer import normalize_windows_element


class WindowsAccessibility(AccessibilityProtocol):
    """
    Windows UI Automation using pywinauto library.

    Provides accurate element coordinates via UIA APIs with stable
    semantic element IDs through the shared registry.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.available = self._check_availability()
        self.pywinauto = None
        self.Desktop = None
        self._registry = VersionedElementRegistry()
        self._cache = AccessibilityCacheManager()
        self._max_depth = 25

        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        if platform.system().lower() != "windows":
            return False
        import importlib.util

        return importlib.util.find_spec("pywinauto") is not None

    def _initialize_api(self) -> None:
        try:
            import pywinauto
            from pywinauto import Desktop

            self.pywinauto = pywinauto
            self.Desktop = Desktop
            Desktop(backend="uia").windows()
        except Exception as e:
            from ....utils.ui import print_warning, print_info

            print_warning(f"UI Automation not available: {e}")
            print_info("May need to run with administrator privileges")
            self.available = False

    def invalidate_cache(self, app_name: Optional[str] = None) -> None:
        self._cache.invalidate(app_name)
        self._registry.advance_epoch("cache_invalidation")

    def get_app(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        if not self.available or not app_name:
            return None

        cache_key = app_name.lower()

        cached = self._cache.get_app(cache_key)
        if cached:
            return cached

        try:
            desktop = self.Desktop(backend="uia")
            for w in desktop.windows():
                title = w.window_text()
                if self._matches_name(title, app_name):
                    self._cache.set_app(cache_key, w)
                    return w
        except Exception:
            pass

        return None

    def get_windows(self, app: Any) -> List[Any]:
        return [app] if app else []

    def get_elements(
        self, app_name: str, interactive_only: bool = True, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        if not self.available:
            return []

        cache_key = f"{app_name.lower()}:{interactive_only}"

        if use_cache:
            cached = self._cache.get_elements(cache_key)
            if cached:
                return cached[1]

        app = self.get_app(app_name)
        if not app:
            return []

        elements: List[Dict[str, Any]] = []
        app_name_lower = app_name.lower()
        self._traverse(app, elements, interactive_only, 0, app_name_lower)

        self._cache.set_elements(cache_key, elements)
        return elements

    def _is_element_interactive(self, node: Any) -> bool:
        """
        Check if element is interactive by querying the API, NOT by control type.

        Uses actual pywinauto methods to determine interactivity:
        - is_enabled(): Is it enabled for interaction?

        Args:
            node: pywinauto element wrapper

        Returns:
            True if element appears to be interactive
        """
        try:
            return node.is_enabled()
        except Exception:
            return False

    def _traverse(
        self,
        node: Any,
        elements: List[Dict[str, Any]],
        interactive_only: bool,
        depth: int = 0,
        app_name: str = "",
    ) -> None:
        """
        Traverse UI Automation tree and register elements.

        Dynamic detection: Elements are registered based on their actual
        capabilities (is_enabled), NOT based on hardcoded control type lists.

        Args:
            node: Current pywinauto element
            elements: List to accumulate elements
            interactive_only: If True, only register interactive elements
            depth: Current traversal depth
            app_name: Application name
        """
        if depth > self._max_depth:
            return

        try:
            if not interactive_only or self._is_element_interactive(node):
                self._register_element(node, app_name, elements)

            try:
                for child in node.children():
                    self._traverse(
                        child, elements, interactive_only, depth + 1, app_name
                    )
            except Exception:
                pass

        except Exception:
            pass

    def _register_element(
        self, node: Any, app_name: str, elements: List[Dict[str, Any]]
    ) -> None:
        normalized = normalize_windows_element(
            node, app_name, self.screen_width, self.screen_height
        )
        if not normalized:
            return

        element_id = self._registry.register_element(normalized)
        normalized["element_id"] = element_id

        is_bottom = (
            normalized["center"][1] > self.screen_height * 0.75
            if normalized["center"]
            else False
        )
        normalized["is_bottom"] = is_bottom
        normalized["title"] = normalized["label"]
        normalized["_element"] = node
        normalized["_app_name"] = app_name

        elements.append(normalized)

    def click_by_id(
        self, element_id: str, click_type: str = "single"
    ) -> Tuple[bool, str]:
        if not self.available:
            return (False, "Accessibility not available")

        record, status = self._registry.get_element(element_id)

        if status == "not_found":
            return (
                False,
                f"Element '{element_id}' not found. Call get_accessible_elements() to refresh.",
            )

        if status == "stale":
            return (
                False,
                f"Element '{element_id}' is STALE (UI may have changed). "
                f"Call get_accessible_elements() to refresh element list.",
            )

        element_info = record.element_info
        node = record.native_ref
        label = element_info.get("label", element_id)
        app_name = element_info.get("app_name", "")

        if node:
            try:
                self._perform_click(node, click_type)
                self._registry.advance_epoch("click")
                self._cache.on_interaction(app_name if app_name else None)
                return (True, f"Clicked '{label}'")
            except Exception:
                pass

        center = element_info.get("center")
        if center and len(center) == 2:
            try:
                import pyautogui

                normalized = (click_type or "single").strip().lower()
                x, y = center

                if normalized == "double":
                    pyautogui.click(x, y, clicks=2)
                elif normalized == "right":
                    pyautogui.click(x, y, button="right")
                else:
                    pyautogui.click(x, y)

                self._registry.advance_epoch("click")
                self._cache.on_interaction(app_name if app_name else None)
                return (True, f"Clicked '{label}' at ({x}, {y})")
            except Exception as e:
                return (False, f"Coordinate click failed: {e}")

        return (False, f"No click method available for '{label}'")

    def _perform_click(self, node: Any, click_type: str = "single") -> None:
        normalized = (click_type or "single").strip().lower()

        if normalized == "double":
            node.click_input(double=True)
        elif normalized == "right":
            node.click_input(button="right")
        else:
            node.click_input()

    def get_frontmost_app(self) -> Optional[str]:
        if not self.available:
            return None

        try:
            desktop = self.Desktop(backend="uia")
            for w in desktop.windows():
                if w.has_focus():
                    return w.window_text()
        except Exception:
            pass
        return None

    def is_app_frontmost(self, app_name: str) -> bool:
        frontmost = self.get_frontmost_app()
        return frontmost is not None and self._matches_name(frontmost, app_name)

    def get_window_bounds(self, app_name: str) -> Optional[Tuple[int, int, int, int]]:
        if not self.available:
            return None

        app = self.get_app(app_name)
        if not app:
            return None

        try:
            rect = app.rectangle()
            return (rect.left, rect.top, rect.width(), rect.height())
        except Exception:
            return None

    def get_running_apps(self) -> List[str]:
        if not self.available:
            return []

        apps = []
        seen = set()
        try:
            desktop = self.Desktop(backend="uia")
            for w in desktop.windows():
                name = w.window_text()
                if name and name not in seen:
                    apps.append(name)
                    seen.add(name)
        except Exception:
            pass
        return apps

    def is_app_running(self, app_name: str) -> bool:
        return self.get_app(app_name) is not None

    def _matches_name(self, name1: str, name2: str) -> bool:
        if not name1 or not name2:
            return False
        n1, n2 = name1.lower(), name2.lower()
        return n1 in n2 or n2 in n1

    def find_element(
        self, app_name: str, label: str, exact_match: bool = False
    ) -> Optional[Dict[str, Any]]:
        elements = self.get_elements(app_name, interactive_only=True)
        label_lower = label.lower()

        for elem in elements:
            elem_label = (elem.get("label") or "").lower()
            elem_id = (elem.get("identifier") or "").lower()

            if exact_match:
                if elem_label == label_lower or elem_id == label_lower:
                    return elem
            else:
                if label_lower in elem_label or label_lower in elem_id:
                    return elem

        return None

    def find_elements(
        self,
        label: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not app_name:
            return []

        elements = self.get_elements(app_name, interactive_only=True)

        if not label and not role:
            return elements

        results = []
        for elem in elements:
            if label:
                elem_label = (elem.get("label") or "").lower()
                elem_id = (elem.get("identifier") or "").lower()
                if label.lower() not in elem_label and label.lower() not in elem_id:
                    continue
            if role and role.lower() not in (elem.get("role") or "").lower():
                continue
            results.append(elem)

        return results

    def click_element(self, label: str, app_name: str) -> Tuple[bool, Optional[Dict]]:
        if not self.available:
            return (False, None)

        element = self.find_element(app_name, label)
        if not element:
            return (False, None)

        element_id = element.get("element_id")
        if element_id:
            success, _ = self.click_by_id(element_id)
            return (success, element)

        return (False, element)

    def get_text(self, app_name: str) -> List[str]:
        if not self.available:
            return []

        texts = []
        seen = set()

        for elem in self.get_elements(
            app_name, interactive_only=False, use_cache=False
        ):
            for key in ("label", "title", "description", "identifier"):
                val = elem.get(key, "")
                if val and val not in seen:
                    texts.append(val)
                    seen.add(val)

        return texts

    def get_element_by_id(self, element_id: str) -> Optional[Dict[str, Any]]:
        record, status = self._registry.get_element(element_id)
        if record:
            return record.element_info
        return None

    def get_all_ui_elements(
        self, app_name: Optional[str] = None, include_menu_bar: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not self.available or not app_name:
            return {
                "interactive": [],
                "menu_bar": [],
                "menu_items": [],
                "static": [],
                "structural": [],
            }

        all_elements = self.get_elements(
            app_name, interactive_only=False, use_cache=False
        )

        categorized = {
            "interactive": [],
            "menu_bar": [],
            "menu_items": [],
            "static": [],
            "structural": [],
        }

        for elem in all_elements:
            role = (elem.get("role") or "").lower()

            if "menubar" in role:
                categorized["menu_bar"].append(elem)
            elif "menu" in role:
                categorized["menu_items"].append(elem)
            elif elem.get("enabled"):
                categorized["interactive"].append(elem)
            elif role in ("text", "image", "statusbar"):
                categorized["static"].append(elem)
            else:
                categorized["structural"].append(elem)

        return categorized

    def get_all_interactive_elements(
        self, app_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not app_name:
            return []
        return self.get_elements(app_name, interactive_only=True)

    def click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> Tuple[bool, str]:
        if not self.available:
            return (False, "unavailable")

        node = element_dict.get("_element")
        if not node:
            return (False, "no_reference")

        try:
            self._perform_click(node)
            self._registry.advance_epoch("click")
            self._cache.on_interaction()
            return (True, "element")
        except Exception:
            pass

        current = node
        for depth in range(1, max_depth + 1):
            try:
                parent = current.parent()
                if parent:
                    try:
                        self._perform_click(parent)
                        self._registry.advance_epoch("click")
                        self._cache.on_interaction()
                        return (True, f"parent_{depth}")
                    except Exception:
                        current = parent
                else:
                    break
            except Exception:
                break

        return (False, "not_clickable")

    def try_click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> Tuple[bool, str]:
        return self.click_element_or_parent(element_dict, max_depth)

    def get_text_from_app(self, app_name: str, role: Optional[str] = None) -> List[str]:
        return self.get_text(app_name)
