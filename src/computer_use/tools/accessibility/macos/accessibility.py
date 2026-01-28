"""
macOS Accessibility API using atomacos for fast, accurate element interaction.

Design principles:
- Use atomacos's native capabilities where reliable
- Integrate with shared registry for stable element IDs
- Use platform normalizer for all role/element conversions
- Consistent API with Windows/Linux implementations
"""

from typing import List, Optional, Dict, Any, Tuple
import platform
import time

from ..protocol import AccessibilityProtocol
from ..element_registry import VersionedElementRegistry
from ..cache_manager import AccessibilityCacheManager
from .role_normalizer import normalize_macos_element


class MacOSAccessibility(AccessibilityProtocol):
    """
    macOS accessibility using atomacos library.

    Provides accurate element coordinates via AX APIs with stable
    semantic element IDs through the shared registry.
    """

    def __init__(self, screen_width: int = 0, screen_height: int = 0):
        if screen_width == 0 or screen_height == 0:
            self.screen_width, self.screen_height = self._detect_screen_size()
        else:
            self.screen_width = screen_width
            self.screen_height = screen_height

        self.available = self._check_availability()
        self.atomacos = None
        self._registry = VersionedElementRegistry()
        self._cache = AccessibilityCacheManager()
        self._max_elements = 500
        self._max_depth = 25

        if self.available:
            self._initialize_api()

    def _detect_screen_size(self) -> Tuple[int, int]:
        try:
            import pyautogui

            size = pyautogui.size()
            return (size.width, size.height)
        except Exception:
            pass

        try:
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen:
                frame = screen.frame()
                backing = screen.backingScaleFactor()
                return (
                    int(frame.size.width * backing),
                    int(frame.size.height * backing),
                )
        except Exception:
            pass

        return (1920, 1080)

    def _check_availability(self) -> bool:
        if platform.system().lower() != "darwin":
            return False
        import importlib.util

        return importlib.util.find_spec("atomacos") is not None

    def _initialize_api(self) -> None:
        try:
            import atomacos

            self.atomacos = atomacos
            atomacos.getAppRefByBundleId("com.apple.finder")
        except Exception as e:
            from ....utils.ui import print_warning, print_info

            print_warning(f"Accessibility not available: {e}")
            print_info(
                "Enable in: System Settings → Privacy & Security → Accessibility"
            )
            self.available = False

    def invalidate_cache(self, app_name: Optional[str] = None) -> None:
        self._cache.invalidate(app_name)
        self._registry.advance_epoch("cache_invalidation")

    def get_app(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        if not self.available or not app_name:
            return None

        app_name = app_name.strip()
        cache_key = app_name.lower()

        cached = self._cache.get_app(cache_key)
        if cached and self._has_windows(cached):
            return cached

        best_candidate = None
        best_has_windows = False

        for attempt in range(retry_count):
            if attempt > 0:
                self._cache.invalidate_app(cache_key)
                time.sleep(0.1)

            try:
                for running_app in self.atomacos.NativeUIElement.getRunningApps():
                    localized_name = None
                    if hasattr(running_app, "localizedName"):
                        localized_name = running_app.localizedName()

                    if localized_name and self._matches_name(localized_name, app_name):
                        bundle_id = None
                        if hasattr(running_app, "bundleIdentifier"):
                            bundle_id = running_app.bundleIdentifier()

                        if bundle_id:
                            try:
                                app_ref = self.atomacos.getAppRefByBundleId(bundle_id)
                                if app_ref and self._is_valid_app_ref(app_ref):
                                    has_windows = self._has_windows(app_ref)
                                    if has_windows:
                                        self._cache.set_app(cache_key, app_ref)
                                        return app_ref
                                    elif not best_candidate:
                                        best_candidate = app_ref
                            except Exception:
                                continue
            except Exception:
                pass

            try:
                frontmost = self.atomacos.getFrontmostApp()
                if frontmost:
                    front_title = getattr(frontmost, "AXTitle", None) or ""
                    if self._matches_name(str(front_title), app_name):
                        if self._has_windows(frontmost):
                            self._cache.set_app(cache_key, frontmost)
                            return frontmost
                        elif not best_candidate:
                            best_candidate = frontmost
            except Exception:
                pass

        if best_candidate:
            self._cache.set_app(cache_key, best_candidate)
            return best_candidate

        return None

    def _has_windows(self, app_ref: Any) -> bool:
        if not app_ref:
            return False
        try:
            windows = getattr(app_ref, "AXWindows", None)
            if windows and len(windows) > 0:
                return True
            children = getattr(app_ref, "AXChildren", None)
            if children:
                for c in children:
                    role = getattr(c, "AXRole", None)
                    if role and str(role) in ("AXWindow", "AXSheet", "AXDrawer"):
                        return True
            return False
        except Exception:
            return False

    def _is_valid_app_ref(self, app_ref: Any) -> bool:
        if not app_ref:
            return False
        try:
            pid = getattr(app_ref, "AXPid", None) or getattr(app_ref, "pid", None)
            if pid and pid > 0:
                return True
            role = getattr(app_ref, "AXRole", None)
            if role == "AXApplication":
                return True
            windows = getattr(app_ref, "AXWindows", None)
            if windows is not None and len(windows) > 0:
                return True
            children = getattr(app_ref, "AXChildren", None)
            if children is not None and len(children) > 0:
                return True
            return bool(role)
        except Exception:
            return False

    def get_windows(self, app: Any) -> List[Any]:
        if not app:
            return []

        try:
            if hasattr(app, "windows"):
                return list(app.windows())
        except Exception:
            pass

        if hasattr(app, "AXWindows") and app.AXWindows:
            return list(app.AXWindows)

        if hasattr(app, "AXChildren") and app.AXChildren:
            return [
                c
                for c in app.AXChildren
                if hasattr(c, "AXRole")
                and str(c.AXRole) in ("AXWindow", "AXSheet", "AXDrawer")
            ]

        return []

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

        windows = self.get_windows(app)

        if hasattr(app, "AXMenuBar"):
            try:
                self._traverse(
                    app.AXMenuBar, elements, interactive_only, 0, app_name_lower
                )
            except Exception:
                pass

        for window in windows:
            self._traverse(window, elements, interactive_only, 0, app_name_lower)

        self._cache.set_elements(cache_key, elements)
        return elements

    def _is_element_interactive(self, node: Any) -> bool:
        """
        Check if element is interactive by querying the API, NOT by role name.

        Uses actual accessibility attributes to determine interactivity:
        - AXActions: Does it have actions?
        - AXEnabled: Is it enabled for interaction?

        Args:
            node: atomacos accessibility node

        Returns:
            True if element appears to be interactive
        """
        try:
            actions = getattr(node, "AXActions", None)
            has_actions = actions is not None and len(actions) > 0
            is_enabled = bool(getattr(node, "AXEnabled", False))
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
    ) -> bool:
        """
        Traverse accessibility tree and register elements.

        Dynamic detection: Elements are registered based on their actual
        capabilities (has_actions, is_enabled), NOT based on hardcoded role lists.

        Args:
            node: Current accessibility node
            elements: List to accumulate elements
            interactive_only: If True, only register interactive elements
            depth: Current traversal depth
            app_name: Application name

        Returns:
            True to continue traversal, False if limits reached
        """
        if depth > self._max_depth or len(elements) >= self._max_elements:
            return False

        try:
            role = str(getattr(node, "AXRole", ""))

            if role == "AXApplication":
                children = getattr(node, "AXChildren", None)
                if children:
                    for child in children:
                        if not self._traverse(
                            child, elements, interactive_only, depth + 1, app_name
                        ):
                            return False
                return True

            if not interactive_only or self._is_element_interactive(node):
                self._register_element(node, app_name, elements)

            children = getattr(node, "AXChildren", None)
            if children:
                for child in children:
                    if not self._traverse(
                        child, elements, interactive_only, depth + 1, app_name
                    ):
                        return False

            return True
        except Exception:
            return True

    def _register_element(
        self, node: Any, app_name: str, elements: List[Dict[str, Any]]
    ) -> None:
        normalized = normalize_macos_element(node, app_name)
        if not normalized:
            return

        if normalized["bounds"][0] > self.screen_width * 2:
            return
        if normalized["bounds"][1] > self.screen_height * 2:
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
        """
        Click element by its unique ID.

        Click priority (in order):
        1. Native accessibility click (Press/AXPress) - WORKS WITHOUT FRONTMOST
        2. Coordinate click via pyautogui - Requires frontmost (fallback only)

        Args:
            element_id: Unique element ID from get_elements
            click_type: single, double, or right

        Returns:
            (success, message) tuple
        """
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
        center = element_info.get("center")
        role = element_info.get("role", "")
        app_name = element_info.get("app_name", "")

        if role in ("StaticText", "Text") and node:
            parent = self._find_clickable_parent(node)
            if parent:
                clicked, message = self._native_click(
                    parent, label, app_name=app_name, click_type=click_type
                )
                if clicked:
                    self._registry.advance_epoch("click")
                    return (clicked, message)

        if node:
            clicked, message = self._native_click(
                node, label, app_name=app_name, click_type=click_type
            )
            if clicked:
                self._registry.advance_epoch("click")
                return (clicked, message)

        normalized = (click_type or "single").strip().lower()
        if normalized not in {"single", "double", "right"}:
            normalized = "single"

        if center and len(center) == 2:
            try:
                import pyautogui

                if normalized == "double":
                    pyautogui.click(center[0], center[1], clicks=2)
                elif normalized == "right":
                    pyautogui.click(center[0], center[1], button="right")
                else:
                    pyautogui.click(center[0], center[1])
                time.sleep(0.05)
                self._registry.advance_epoch("click")
                self._cache.on_interaction(app_name if app_name else None)
                return (
                    True,
                    f"Clicked '{label}' at {tuple(center)} (coordinate fallback)",
                )
            except Exception as e:
                return (False, f"Click failed: {e}")

        return (False, f"No click method for '{label}'")

    def _native_click(
        self, node: Any, label: str, app_name: str = "", click_type: str = "single"
    ) -> Tuple[bool, str]:
        invalidate_target = app_name if app_name else None
        normalized = (click_type or "single").strip().lower()
        if normalized not in {"single", "double", "right"}:
            normalized = "single"

        try:
            if normalized == "single":
                if hasattr(node, "Press") and callable(getattr(node, "Press")):
                    node.Press()
                    time.sleep(0.05)
                    self._cache.on_interaction(invalidate_target)
                    return (True, f"Clicked '{label}' via Press")

                if hasattr(node, "AXPress") and callable(getattr(node, "AXPress")):
                    node.AXPress()
                    time.sleep(0.05)
                    self._cache.on_interaction(invalidate_target)
                    return (True, f"Clicked '{label}' via AXPress")

            preferred_substrings: Tuple[str, ...]
            if normalized == "right":
                preferred_substrings = ("showmenu", "context", "menu", "secondary")
            elif normalized == "double":
                preferred_substrings = ("double", "open", "confirm")
            else:
                preferred_substrings = ("press", "click")

            actions = self._get_available_actions(node)
            for action in actions:
                action_lower = action.lower()
                if any(s in action_lower for s in preferred_substrings):
                    if hasattr(node, action) and callable(getattr(node, action)):
                        getattr(node, action)()
                        time.sleep(0.05)
                        self._cache.on_interaction(invalidate_target)
                        return (True, f"Clicked '{label}' via {action}")

                    if hasattr(node, "performAction") and callable(
                        getattr(node, "performAction")
                    ):
                        node.performAction(action)
                        time.sleep(0.05)
                        self._cache.on_interaction(invalidate_target)
                        return (True, f"Clicked '{label}' via {action}")

            if normalized in {"double", "right"}:
                return (False, f"No native {normalized}-click action for '{label}'")

            return (False, f"No native click action for '{label}'")
        except Exception as e:
            return (False, f"Native click failed: {e}")

    def _get_available_actions(self, node: Any) -> List[str]:
        try:
            if hasattr(node, "getActions"):
                actions = node.getActions()
                if actions:
                    return [str(a) for a in actions]
        except Exception:
            pass

        try:
            actions = getattr(node, "AXActions", None)
            if actions:
                return [str(a) for a in actions]
        except Exception:
            pass

        return []

    def _find_clickable_parent(self, node: Any, max_depth: int = 5) -> Optional[Any]:
        """
        Find a clickable parent element for text elements.

        Uses dynamic detection: checks if parent has actions, NOT based on
        hardcoded role lists. Any parent with Press/AXPress/AXActions is clickable.

        Args:
            node: Starting node
            max_depth: Maximum levels to traverse up

        Returns:
            Clickable parent node, or None if not found
        """
        try:
            current = node
            for _ in range(max_depth):
                if not hasattr(current, "AXParent") or not current.AXParent:
                    break
                current = current.AXParent

                if (
                    hasattr(current, "Press")
                    or hasattr(current, "AXPress")
                    or (hasattr(current, "AXActions") and current.AXActions)
                ):
                    return current
        except Exception:
            pass

        return None

    def get_frontmost_app(self) -> Optional[str]:
        if not self.available:
            return None

        try:
            from AppKit import NSWorkspace

            frontmost = NSWorkspace.sharedWorkspace().frontmostApplication()
            if frontmost:
                name = frontmost.localizedName()
                if name:
                    return name
        except Exception:
            pass

        try:
            app = self.atomacos.getFrontmostApp()
            if app:
                return getattr(app, "AXTitle", None)
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

        windows = self.get_windows(app)
        if not windows:
            return None

        try:
            w = windows[0]
            pos = w.AXPosition
            size = w.AXSize
            return (int(pos[0]), int(pos[1]), int(size[0]), int(size[1]))
        except Exception:
            return None

    def get_running_apps(self) -> List[str]:
        if not self.available:
            return []

        apps = []
        try:
            for running_app in self.atomacos.NativeUIElement.getRunningApps():
                localized_name = None
                if hasattr(running_app, "localizedName"):
                    localized_name = running_app.localizedName()
                if localized_name:
                    apps.append(localized_name)
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
        label_lower = label.lower()

        for elem in self.get_elements(app_name, interactive_only=True):
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

            if role:
                if role.lower() not in (elem.get("role") or "").lower():
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
        seen: set = set()

        for elem in self.get_elements(
            app_name, interactive_only=False, use_cache=False
        ):
            for key in ("label", "title", "description"):
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
        empty = {
            "interactive": [],
            "menu_bar": [],
            "menu_items": [],
            "static": [],
            "structural": [],
        }

        if not self.available or not app_name:
            return empty

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
            role = elem.get("role", "").lower()

            if "menu" in role and "bar" in role:
                categorized["menu_bar"].append(elem)
            elif "menu" in role:
                categorized["menu_items"].append(elem)
            elif elem.get("has_actions") or elem.get("enabled"):
                categorized["interactive"].append(elem)
            elif role in ("statictext", "text", "label", "image"):
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

        label = element_dict.get("label", "element")
        app_name = element_dict.get("_app_name", "")

        result = self._native_click(node, label, app_name)
        if result[0]:
            return (True, "element")

        current = node
        for depth in range(1, max_depth + 1):
            try:
                if hasattr(current, "AXParent") and current.AXParent:
                    parent = current.AXParent
                    result = self._native_click(parent, label, app_name)
                    if result[0]:
                        return (True, f"parent_{depth}")
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
