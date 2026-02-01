"""
Linux AT-SPI accessibility API using pyatspi for fast, accurate element interaction.

Design principles:
- Let the API tell us what's interactive (has actions/is enabled)
- Integrate with shared registry for stable element IDs
- Use platform normalizer for all role/element conversions
- Consistent API with macOS/Windows implementations
"""

from typing import List, Optional, Dict, Any, Tuple
import threading
import platform

from ..protocol import AccessibilityProtocol
from ..element_store import SimpleElementStore
from ..cache_manager import AccessibilityCacheManager
from .role_normalizer import normalize_linux_element


class LinuxAccessibility(AccessibilityProtocol):
    """
    Linux AT-SPI using pyatspi library.

    Provides accurate element coordinates via AT-SPI APIs with stable
    semantic element IDs through the shared registry.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.available = self._check_availability()
        self.pyatspi = None
        self.desktop = None
        self._store = SimpleElementStore()
        self._cache = AccessibilityCacheManager()
        self._max_depth = 25
        self._lock = threading.RLock()

        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        if platform.system().lower() != "linux":
            return False
        import importlib.util

        return importlib.util.find_spec("pyatspi") is not None

    def _initialize_api(self) -> None:
        try:
            import pyatspi

            self.pyatspi = pyatspi
            self.desktop = pyatspi.Registry.getDesktop(0)
            list(self.desktop)
        except Exception as e:
            from ....utils.ui import print_warning, print_info

            print_warning(f"AT-SPI not available: {e}")
            print_info("Ensure accessibility is enabled in system settings")
            self.available = False

    def _run_accessibility(self, func, *args, **kwargs):
        from ....utils.threading.main_thread import run_on_main_thread

        def _call():
            with self._lock:
                return func(*args, **kwargs)

        return run_on_main_thread(_call)

    def invalidate_cache(self, app_name: Optional[str] = None) -> None:
        with self._lock:
            self._cache.invalidate(app_name)
            if app_name:
                self._store.clear_app(app_name)
            else:
                self._store.clear_all()

    def get_app(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        return self._run_accessibility(self._get_app_impl, app_name, retry_count)

    def _get_app_impl(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        if not self.available or not app_name:
            return None

        cache_key = app_name.lower()

        cached = self._cache.get_app(cache_key)
        if cached:
            return cached

        try:
            for app in self.desktop:
                name = getattr(app, "name", "")
                if name and self._matches_name(name, app_name):
                    self._cache.set_app(cache_key, app)
                    return app
        except Exception:
            pass

        return None

    def get_windows(self, app: Any) -> List[Any]:
        return self._run_accessibility(self._get_windows_impl, app)

    def _get_windows_impl(self, app: Any) -> List[Any]:
        if not app:
            return []

        windows = []
        try:
            for i in range(app.childCount):
                try:
                    child = app.getChildAtIndex(i)
                    role = child.getRoleName().lower()
                    if role in ("frame", "window", "dialog"):
                        windows.append(child)
                except Exception:
                    continue
        except Exception:
            pass

        return windows

    def get_elements(
        self, app_name: str, interactive_only: bool = True, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        return self._run_accessibility(
            self._get_elements_impl, app_name, interactive_only, use_cache
        )

    def _get_elements_impl(
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
        for window in self.get_windows(app):
            self._traverse(window, elements, interactive_only, 0, app_name_lower)

        self._cache.set_elements(cache_key, elements)
        return elements

    def _is_element_interactive(self, node: Any) -> bool:
        """
        Check if element is interactive by querying the API, NOT by role name.

        Uses actual AT-SPI methods to determine interactivity:
        - queryAction().nActions: Does it have actions?
        - getState().contains(STATE_ENABLED): Is it enabled?

        Args:
            node: pyatspi accessible node

        Returns:
            True if element appears to be interactive
        """
        try:
            has_actions = False
            try:
                action_iface = node.queryAction()
                has_actions = action_iface.nActions > 0
            except Exception:
                pass

            is_enabled = False
            try:
                state_set = node.getState()
                is_enabled = state_set.contains(self.pyatspi.STATE_ENABLED)
            except Exception:
                pass

            return has_actions or is_enabled
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
        Traverse AT-SPI tree and register elements.

        Dynamic detection: Elements are registered based on their actual
        capabilities (has_actions, is_enabled), NOT based on hardcoded role lists.

        Args:
            node: Current pyatspi accessible node
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

            for i in range(node.childCount):
                try:
                    child = node.getChildAtIndex(i)
                    self._traverse(
                        child, elements, interactive_only, depth + 1, app_name
                    )
                except Exception:
                    continue

        except Exception:
            pass

    def _register_element(
        self, node: Any, app_name: str, elements: List[Dict[str, Any]]
    ) -> None:
        normalized = normalize_linux_element(
            node, self.pyatspi, app_name, self.screen_width, self.screen_height
        )
        if not normalized:
            return

        normalized["_native_ref"] = node
        element_id = self._store.store(normalized, app_name)
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
        return self._run_accessibility(self._click_by_id_impl, element_id, click_type)

    def _click_by_id_impl(
        self, element_id: str, click_type: str = "single"
    ) -> Tuple[bool, str]:
        if not self.available:
            return (False, "Accessibility not available")

        element = self._store.get(element_id)

        if not element:
            return (
                False,
                f"Element '{element_id}' not found. Call get_accessible_elements() to refresh.",
            )

        node = element.get("_native_ref") or element.get("_element")
        label = element.get("label", element_id)
        app_name = element.get("app_name", "")

        if not node:
            return (False, f"Element '{element_id}' has no native reference.")

        try:
            self._perform_click(node, click_type)
            self._cache.on_interaction(app_name if app_name else None)
            return (True, f"Clicked '{label}'")
        except Exception as e:
            return (
                False,
                f"Click failed for '{label}': {e}. UI may have changed - call get_accessible_elements() to refresh.",
            )

    def _perform_click(self, node: Any, click_type: str = "single") -> None:
        normalized = (click_type or "single").strip().lower()

        action_iface = node.queryAction()

        action_map = {
            "single": ("click", "press", "activate"),
            "double": ("double", "open", "activate"),
            "right": ("context", "menu", "popup"),
        }

        preferred = action_map.get(normalized, action_map["single"])

        for i in range(action_iface.nActions):
            action_name = action_iface.getName(i).lower()
            if any(p in action_name for p in preferred):
                action_iface.doAction(i)
                return

        for i in range(action_iface.nActions):
            action_name = action_iface.getName(i).lower()
            if "click" in action_name or "press" in action_name:
                action_iface.doAction(i)
                return

        raise Exception("No click/press action available")

    def get_frontmost_app(self) -> Optional[str]:
        return self._run_accessibility(self._get_frontmost_app_impl)

    def _get_frontmost_app_impl(self) -> Optional[str]:
        if not self.available:
            return None

        try:
            for app in self.desktop:
                for i in range(app.childCount):
                    try:
                        window = app.getChildAtIndex(i)
                        state_set = window.getState()
                        if state_set.contains(self.pyatspi.STATE_ACTIVE):
                            return app.name
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def is_app_frontmost(self, app_name: str) -> bool:
        frontmost = self.get_frontmost_app()
        return frontmost is not None and self._matches_name(frontmost, app_name)

    def get_window_bounds(self, app_name: str) -> Optional[Tuple[int, int, int, int]]:
        return self._run_accessibility(self._get_window_bounds_impl, app_name)

    def _get_window_bounds_impl(
        self, app_name: str
    ) -> Optional[Tuple[int, int, int, int]]:
        if not self.available:
            return None

        app = self.get_app(app_name)
        if not app:
            return None

        windows = self.get_windows(app)
        if not windows:
            return None

        try:
            component = windows[0].queryComponent()
            extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)
            x, y, w, h = extents.x, extents.y, extents.width, extents.height
            return (int(x), int(y), int(w), int(h))
        except Exception:
            return None

    def get_running_apps(self) -> List[str]:
        return self._run_accessibility(self._get_running_apps_impl)

    def _get_running_apps_impl(self) -> List[str]:
        if not self.available:
            return []

        apps = []
        try:
            for app in self.desktop:
                name = getattr(app, "name", "")
                if name:
                    apps.append(name)
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
        return self._store.get(element_id)

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

            if "menu" in role and "bar" in role:
                categorized["menu_bar"].append(elem)
            elif "menu" in role:
                categorized["menu_items"].append(elem)
            elif elem.get("has_actions") or elem.get("enabled"):
                categorized["interactive"].append(elem)
            elif role in ("label", "static", "heading", "paragraph", "image", "icon"):
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

        node = element_dict.get("_native_ref") or element_dict.get("_element")
        if not node:
            return (False, "no_reference")

        try:
            self._perform_click(node)
            self._cache.on_interaction()
            return (True, "element")
        except Exception:
            pass

        current = node
        for depth in range(1, max_depth + 1):
            try:
                if hasattr(current, "getParent"):
                    parent = current.getParent()
                    if parent:
                        try:
                            self._perform_click(parent)
                            self._cache.on_interaction()
                            return (True, f"parent_{depth}")
                        except Exception:
                            current = parent
                    else:
                        break
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
