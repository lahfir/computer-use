"""
macOS Accessibility API using atomacos for fast, accurate element interaction.

Design principles:
- Use atomacos's native capabilities where reliable
- Integrate with shared registry for stable element IDs
- Use platform normalizer for all role/element conversions
- Consistent API with Windows/Linux implementations
"""

from typing import List, Optional, Dict, Any, Tuple
import threading
import platform
import time

from ..protocol import AccessibilityProtocol
from ..element_store import SimpleElementStore
from ..cache_manager import AccessibilityCacheManager
from .role_normalizer import normalize_macos_element


def _is_nonempty_list(value: Any) -> bool:
    """
    Safely check if value is a non-empty list-like object.
    Handles OC_PythonLong and other scalar types that don't support len().
    """
    if value is None:
        return False
    try:
        return (
            hasattr(value, "__iter__") and not isinstance(value, str) and len(value) > 0
        )
    except TypeError:
        return False


def _safe_iter(value: Any) -> list:
    """
    Safely iterate over a value that might be OC_PythonLong or None.
    Returns empty list if value is not iterable.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return []
    try:
        if hasattr(value, "__iter__"):
            return list(value)
        return []
    except (TypeError, ValueError):
        return []


def _safe_str(value: Any, max_len: int = 100) -> str:
    """
    Safely convert a value to string. Handles atomacos objects that crash on str().
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:max_len] if len(value) > max_len else value
    if isinstance(value, (int, float)):
        return str(value)
    try:
        result = str(value)
        return result[:max_len] if len(result) > max_len else result
    except (TypeError, ValueError, AttributeError):
        return ""


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
        self._store = SimpleElementStore()
        self._cache = AccessibilityCacheManager()
        self._max_elements = 500
        self._max_depth = 25
        self._lock = threading.RLock()

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

    def _run_accessibility(self, func, *args, **kwargs):
        with self._lock:
            return func(*args, **kwargs)

    def invalidate_cache(self, app_name: Optional[str] = None) -> None:
        with self._lock:
            self._cache.invalidate(app_name)
            if app_name:
                self._store.clear_app(app_name)
            else:
                self._store.clear_all()

    def get_app(self, app_name: str, retry_count: int = 1) -> Optional[Any]:
        return self._run_accessibility(self._get_app_impl, app_name, retry_count)

    def _get_app_impl(self, app_name: str, retry_count: int = 1) -> Optional[Any]:
        """
        Get application reference using scored candidate selection.

        Collects all matching candidates, scores them, and returns the
        highest-scored candidate with windows. No retry loops or sleeps.

        Args:
            app_name: Name of the application to find
            retry_count: Deprecated, kept for API compatibility

        Returns:
            Application reference or None if not found
        """
        if not self.available or not app_name:
            return None

        app_name = app_name.strip()
        cache_key = app_name.lower()

        cached = self._cache.get_app(cache_key)
        if cached and self._has_windows(cached):
            return cached

        candidates = []

        try:
            for running_app in self.atomacos.NativeUIElement.getRunningApps():
                localized_name = None
                if hasattr(running_app, "localizedName"):
                    localized_name = running_app.localizedName()

                if not localized_name:
                    continue

                if not self._matches_name(localized_name, app_name):
                    continue

                bundle_id = None
                if hasattr(running_app, "bundleIdentifier"):
                    bundle_id = running_app.bundleIdentifier()

                score = self._score_app_match(localized_name, app_name, bundle_id or "")
                candidates.append((score, localized_name, bundle_id, running_app))
        except Exception:
            pass

        candidates.sort(key=lambda x: -x[0])

        for score, name, bundle_id, running_app in candidates:
            if not bundle_id:
                continue
            try:
                app_ref = self.atomacos.getAppRefByBundleId(bundle_id)
                if app_ref and self._has_windows(app_ref):
                    self._cache.set_app(cache_key, app_ref)
                    return app_ref
            except Exception:
                continue

        for score, name, bundle_id, running_app in candidates:
            if not bundle_id:
                continue
            try:
                app_ref = self.atomacos.getAppRefByBundleId(bundle_id)
                if app_ref and self._is_valid_app_ref(app_ref):
                    self._cache.set_app(cache_key, app_ref)
                    return app_ref
            except Exception:
                continue

        try:
            frontmost = self.atomacos.getFrontmostApp()
            if frontmost:
                front_title = getattr(frontmost, "AXTitle", None) or ""
                if self._matches_name(str(front_title), app_name):
                    self._cache.set_app(cache_key, frontmost)
                    return frontmost
        except Exception:
            pass

        return None

    def _has_windows(self, app_ref: Any) -> bool:
        if not app_ref:
            return False
        try:
            windows = getattr(app_ref, "AXWindows", None)
            if _is_nonempty_list(windows):
                return True
            children = getattr(app_ref, "AXChildren", None)
            for c in _safe_iter(children):
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
            if _is_nonempty_list(windows):
                return True
            children = getattr(app_ref, "AXChildren", None)
            if _is_nonempty_list(children):
                return True
            return bool(role)
        except Exception:
            return False

    def get_windows(self, app: Any) -> List[Any]:
        return self._run_accessibility(self._get_windows_impl, app)

    def _get_windows_impl(self, app: Any) -> List[Any]:
        if not app:
            return []

        try:
            if hasattr(app, "windows"):
                return list(app.windows())
        except Exception:
            pass

        windows_attr = getattr(app, "AXWindows", None)
        if _is_nonempty_list(windows_attr):
            return _safe_iter(windows_attr)

        children_attr = getattr(app, "AXChildren", None)
        if _is_nonempty_list(children_attr):
            return [
                c
                for c in _safe_iter(children_attr)
                if hasattr(c, "AXRole")
                and str(c.AXRole) in ("AXWindow", "AXSheet", "AXDrawer")
            ]

        return []

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

        windows = self.get_windows(app)

        if hasattr(app, "AXMenuBar"):
            try:
                self._traverse(
                    app.AXMenuBar, elements, interactive_only, 0, app_name_lower
                )
            except Exception:
                pass

        if hasattr(app, "AXToolbar"):
            try:
                self._traverse(
                    app.AXToolbar, elements, interactive_only, 0, app_name_lower
                )
            except Exception:
                pass

        app_children = getattr(app, "AXChildren", None)
        if _is_nonempty_list(app_children):
            for child in _safe_iter(app_children):
                child_role = str(getattr(child, "AXRole", "") or "")
                if child_role not in ("AXWindow", "AXMenuBar", "AXSheet", "AXDrawer"):
                    try:
                        self._traverse(
                            child, elements, interactive_only, 0, app_name_lower
                        )
                    except Exception:
                        pass

        for window in windows:
            self._traverse(window, elements, interactive_only, 0, app_name_lower)
            if hasattr(window, "AXToolbar"):
                try:
                    self._traverse(
                        window.AXToolbar, elements, interactive_only, 0, app_name_lower
                    )
                except Exception:
                    pass

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
            has_actions = _is_nonempty_list(actions)
            is_enabled = bool(getattr(node, "AXEnabled", False))
            return has_actions or is_enabled
        except Exception:
            return False

    def _batch_fetch_attributes(self, node: Any) -> Optional[Dict[str, Any]]:
        """
        Fetch all accessibility attributes for a node with per-attribute error handling.

        Some elements throw exceptions for unsupported attributes (e.g., AXValue
        on MenuButton). Each attribute is fetched individually to prevent one
        failure from losing all data.

        Args:
            node: atomacos accessibility node

        Returns:
            Dictionary of all attributes, or None if critical attrs failed
        """
        try:
            role = str(getattr(node, "AXRole", "") or "")
        except Exception:
            return None

        try:
            position = getattr(node, "AXPosition", None)
        except Exception:
            position = None

        try:
            size = getattr(node, "AXSize", None)
        except Exception:
            size = None

        def safe_get(attr: str, default: Any = None) -> Any:
            try:
                return getattr(node, attr, default)
            except Exception:
                return default

        def safe_str(attr: str) -> str:
            try:
                val = getattr(node, attr, None)
                return str(val) if val else ""
            except Exception:
                return ""

        return {
            "role": role,
            "position": position,
            "size": size,
            "title": safe_get("AXTitle"),
            "description": safe_get("AXDescription"),
            "value": safe_get("AXValue"),
            "placeholder": safe_get("AXPlaceholderValue"),
            "identifier": safe_str("AXIdentifier"),
            "actions": safe_get("AXActions") or [],
            "enabled": bool(safe_get("AXEnabled", False)),
            "focused": bool(safe_get("AXFocused", False)),
            "role_description": safe_str("AXRoleDescription"),
            "help": safe_str("AXHelp"),
            "children": safe_get("AXChildren"),
        }

    def _traverse(
        self,
        node: Any,
        elements: List[Dict[str, Any]],
        interactive_only: bool,
        depth: int = 0,
        app_name: str = "",
    ) -> bool:
        """
        Traverse accessibility tree and register elements using batch attribute fetch.

        Uses _batch_fetch_attributes() to minimize IPC calls to the macOS
        accessibility daemon. All attributes are fetched once per node.

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

        attrs = self._batch_fetch_attributes(node)
        if attrs is None:
            return True

        role = attrs["role"]

        if role == "AXApplication":
            children = attrs["children"]
            for child in _safe_iter(children):
                if not self._traverse(
                    child, elements, interactive_only, depth + 1, app_name
                ):
                    return False
            return True

        has_actions = _is_nonempty_list(attrs["actions"])
        is_interactive = has_actions or attrs["enabled"]

        if not interactive_only or is_interactive:
            self._register_element_from_attrs(node, attrs, app_name, elements)

        children = attrs["children"]
        for child in _safe_iter(children):
            if not self._traverse(
                child, elements, interactive_only, depth + 1, app_name
            ):
                return False

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

    def _register_element_from_attrs(
        self,
        node: Any,
        attrs: Dict[str, Any],
        app_name: str,
        elements: List[Dict[str, Any]],
    ) -> None:
        """
        Register element using pre-fetched attributes (no additional IPC calls).

        Args:
            node: The native accessibility node reference
            attrs: Pre-fetched attributes from _batch_fetch_attributes()
            app_name: Application name
            elements: List to append the registered element to
        """
        pos = attrs.get("position")
        size = attrs.get("size")

        if pos is None or size is None:
            return

        try:
            x, y = pos[0], pos[1]
            w, h = size[0], size[1]
        except (IndexError, TypeError):
            return

        if w <= 0 or h <= 0:
            return

        identifier = attrs.get("identifier", "")
        short_id = identifier if identifier and len(identifier) <= 10 else ""

        label = (
            _safe_str(attrs.get("title"))
            or _safe_str(attrs.get("description"))
            or _safe_str(attrs.get("value"))
            or _safe_str(attrs.get("placeholder"))
            or _safe_str(attrs.get("help"))
            or _safe_str(attrs.get("role_description"))
            or short_id
            or ""
        )

        center = [int(x + w / 2), int(y + h / 2)]

        normalized = {
            "role": self._normalize_role(attrs["role"]),
            "label": label,
            "identifier": identifier,
            "app_name": app_name,
            "center": center,
            "bounds": [int(x), int(y), int(w), int(h)],
            "has_actions": _is_nonempty_list(attrs.get("actions")),
            "enabled": attrs.get("enabled", True),
            "focused": attrs.get("focused", False),
            "_native_ref": node,
        }

        if normalized["bounds"][0] > self.screen_width * 2:
            return
        if normalized["bounds"][1] > self.screen_height * 2:
            return

        element_id = self._store.store(normalized, app_name)
        normalized["element_id"] = element_id
        normalized["is_bottom"] = normalized["center"][1] > self.screen_height * 0.75
        normalized["title"] = label
        normalized["_element"] = node
        normalized["_app_name"] = app_name

        elements.append(normalized)

    def _normalize_role(self, ax_role: str) -> str:
        """
        Normalize macOS AX role to cross-platform role name.

        Args:
            ax_role: macOS accessibility role (e.g., "AXButton")

        Returns:
            Normalized role name (e.g., "Button")
        """
        role_map = {
            "AXButton": "Button",
            "AXTextField": "TextField",
            "AXTextArea": "TextArea",
            "AXStaticText": "StaticText",
            "AXCheckBox": "CheckBox",
            "AXRadioButton": "RadioButton",
            "AXPopUpButton": "PopUpButton",
            "AXComboBox": "ComboBox",
            "AXMenuItem": "MenuItem",
            "AXMenuBarItem": "MenuBarItem",
            "AXMenuButton": "MenuButton",
            "AXGroup": "Group",
            "AXCell": "Cell",
            "AXRow": "Row",
            "AXScrollBar": "ScrollBar",
            "AXTable": "Table",
            "AXImage": "Image",
        }
        return role_map.get(
            ax_role, ax_role.replace("AX", "") if ax_role.startswith("AX") else ax_role
        )

    def click_by_id(
        self, element_id: str, click_type: str = "single"
    ) -> Tuple[bool, str]:
        return self._run_accessibility(self._click_by_id_impl, element_id, click_type)

    def _click_by_id_impl(
        self, element_id: str, click_type: str = "single"
    ) -> Tuple[bool, str]:
        """
        Click element by its unique ID.

        Simple lookup and click - no staleness checks. If click fails,
        return error suggesting to refresh elements.

        Args:
            element_id: Unique element ID from get_elements
            click_type: single, double, or right

        Returns:
            (success, message) tuple
        """
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
        role = element.get("role", "")
        app_name = element.get("app_name", "")

        if not node:
            return (False, f"Element '{element_id}' has no native reference.")

        if role in ("StaticText", "Text"):
            parent = self._find_clickable_parent(node)
            if parent:
                clicked, message = self._native_click(
                    parent, label, app_name=app_name, click_type=click_type
                )
                if clicked:
                    return (clicked, message)

        clicked, message = self._native_click(
            node, label, app_name=app_name, click_type=click_type, role=role
        )
        if clicked:
            return (clicked, message)

        return (
            False,
            f"Click failed for '{label}'. UI may have changed - call get_accessible_elements() to refresh.",
        )

    def _native_click(
        self,
        node: Any,
        label: str,
        app_name: str = "",
        click_type: str = "single",
        role: str = "",
    ) -> Tuple[bool, str]:
        invalidate_target = app_name if app_name else None
        normalized = (click_type or "single").strip().lower()
        if normalized not in {"single", "double", "right"}:
            normalized = "single"

        is_input_field = role.lower() in (
            "textfield",
            "searchfield",
            "textarea",
            "combobox",
        )

        def check_focus_suffix() -> str:
            if not is_input_field:
                return ""
            try:
                focused = bool(getattr(node, "AXFocused", False))
                if focused:
                    return " - element now has keyboard focus, ready for type_text"
            except Exception:
                pass
            return ""

        ui_settle_delay = 0.3

        try:
            if normalized == "single":
                if hasattr(node, "Press") and callable(getattr(node, "Press")):
                    node.Press()
                    time.sleep(ui_settle_delay)
                    self._cache.on_interaction(invalidate_target)
                    return (True, f"Clicked '{label}' via Press{check_focus_suffix()}")

                if hasattr(node, "AXPress") and callable(getattr(node, "AXPress")):
                    node.AXPress()
                    time.sleep(ui_settle_delay)
                    self._cache.on_interaction(invalidate_target)
                    return (True, f"Clicked '{label}' via AXPress{check_focus_suffix()}")

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
                        time.sleep(ui_settle_delay)
                        self._cache.on_interaction(invalidate_target)
                        return (True, f"Clicked '{label}' via {action}{check_focus_suffix()}")

                    if hasattr(node, "performAction") and callable(
                        getattr(node, "performAction")
                    ):
                        node.performAction(action)
                        time.sleep(ui_settle_delay)
                        self._cache.on_interaction(invalidate_target)
                        return (True, f"Clicked '{label}' via {action}{check_focus_suffix()}")

            if normalized in {"double", "right"}:
                return (False, f"No native {normalized}-click action for '{label}'")

            return (False, f"No native click action for '{label}'")
        except Exception as e:
            return (False, f"Native click failed: {e}")

    def _get_available_actions(self, node: Any) -> List[str]:
        try:
            if hasattr(node, "getActions"):
                actions = node.getActions()
                if _is_nonempty_list(actions):
                    return [str(a) for a in _safe_iter(actions)]
        except Exception:
            pass

        try:
            actions = getattr(node, "AXActions", None)
            if _is_nonempty_list(actions):
                return [str(a) for a in _safe_iter(actions)]
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
                    or _is_nonempty_list(getattr(current, "AXActions", None))
                ):
                    return current
        except Exception:
            pass

        return None

    def get_frontmost_app(self) -> Optional[str]:
        return self._run_accessibility(self._get_frontmost_app_impl)

    def _get_frontmost_app_impl(self) -> Optional[str]:
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
            w = windows[0]
            pos = w.AXPosition
            size = w.AXSize
            return (int(pos[0]), int(pos[1]), int(size[0]), int(size[1]))
        except Exception:
            return None

    def get_running_apps(self) -> List[str]:
        return self._run_accessibility(self._get_running_apps_impl)

    def _get_running_apps_impl(self) -> List[str]:
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

    def _score_app_match(
        self, candidate_name: str, search_name: str, bundle_id: str
    ) -> int:
        """
        Score how well a candidate app matches the search name.

        Higher scores indicate better matches. Penalizes helper processes.

        Args:
            candidate_name: Name of the running application
            search_name: Name the user searched for
            bundle_id: Bundle identifier of the app

        Returns:
            Integer score (higher = better match)
        """
        score = 0
        cn = candidate_name.lower()
        sn = search_name.lower()
        bid = (bundle_id or "").lower()

        if cn == sn:
            score += 1000

        if cn.startswith(sn):
            score += 500

        helper_name_patterns = [
            "helper",
            "agent",
            "service",
            "renderer",
            "gpu",
            "web content",
            "extension",
            "xpc",
        ]
        if any(p in cn for p in helper_name_patterns):
            score -= 500

        helper_bundle_patterns = [".helper", ".agent", "xpcservice", ".renderer"]
        if any(p in bid for p in helper_bundle_patterns):
            score -= 500

        score -= len(candidate_name) // 5

        return score

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
        return self._store.get(element_id)

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
