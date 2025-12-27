"""
macOS Accessibility API using atomacos for fast, accurate element interaction.

Design principles:
- Use atomacos's native capabilities where reliable
- Element registry with unique IDs for direct clicks
- Cache invalidation after interactions
- Consistent API with Windows/Linux implementations
"""

from typing import List, Optional, Dict, Any, Tuple
import platform
import time
import uuid

from ...utils.ui import print_warning, print_info


class MacOSAccessibility:
    """
    macOS accessibility using atomacos library.

    Provides accurate element coordinates via AX APIs with an element
    registry pattern - each element gets a unique ID for direct clicks.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        """
        Initialize macOS accessibility.

        Args:
            screen_width: Screen width for bounds validation
            screen_height: Screen height for bounds validation
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.available = self._check_availability()
        self.atomacos = None
        self._app_cache: Dict[str, Any] = {}
        self._element_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._element_registry: Dict[str, Dict[str, Any]] = {}
        self._last_interaction_time: float = 0

        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        """Check if atomacos is available on macOS."""
        if platform.system().lower() != "darwin":
            return False
        import importlib.util

        return importlib.util.find_spec("atomacos") is not None

    def _initialize_api(self) -> None:
        """Initialize atomacos and verify accessibility permissions."""
        try:
            import atomacos

            self.atomacos = atomacos
            atomacos.getAppRefByBundleId("com.apple.finder")
            from ...utils.ui import print_verbose_only

            print_verbose_only("✓ Accessibility API ready")
        except Exception as e:
            print_warning(f"Accessibility not available: {e}")
            print_info(
                "Enable in: System Settings → Privacy & Security → Accessibility"
            )
            self.available = False

    def clear_cache(self) -> None:
        """Clear all caches to force fresh lookups."""
        self._app_cache.clear()
        self._element_cache.clear()

    def invalidate_cache(self) -> None:
        """Invalidate caches after interactions."""
        self._element_cache.clear()
        self._element_registry.clear()
        self._last_interaction_time = time.time()

    def set_active_app(self, app_name: str) -> None:
        """Set and cache the active application."""
        self._element_cache.clear()
        self.get_app(app_name)

    def get_app(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        """
        Get application reference by name using smart matching with retry.

        Strategy:
        1. Check cache
        2. Try atomacos getAppRefByLocalizedName
        3. Smart fallback: Use NSRunningApplication's localizedName()
        4. Fallback: Check if frontmost app matches
        5. Retry with cache clear if not found

        Args:
            app_name: Application name (case-insensitive partial match)
            retry_count: Number of retry attempts

        Returns:
            App reference or None
        """
        if not self.available or not app_name:
            return None

        app_name = app_name.strip()
        cache_key = app_name.lower()

        for attempt in range(retry_count):
            if attempt > 0:
                self._app_cache.pop(cache_key, None)
                time.sleep(0.3)

            if cache_key in self._app_cache:
                return self._app_cache[cache_key]

            try:
                app = self.atomacos.getAppRefByLocalizedName(app_name)
                if app:
                    self._app_cache[cache_key] = app
                    return app
            except Exception:
                pass

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
                                if app_ref:
                                    self._app_cache[cache_key] = app_ref
                                    return app_ref
                            except Exception:
                                continue
            except Exception:
                pass

            try:
                frontmost = self.atomacos.getFrontmostApp()
                if frontmost:
                    front_title = getattr(frontmost, "AXTitle", None) or ""
                    if self._matches_name(str(front_title), app_name):
                        self._app_cache[cache_key] = frontmost
                        return frontmost
            except Exception:
                pass

        return None

    def get_windows(self, app: Any) -> List[Any]:
        """Get all windows for an application."""
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
        """
        Get UI elements from an application.

        Args:
            app_name: Application name
            interactive_only: Only return interactive elements
            use_cache: Use cached elements if available

        Returns:
            List of element dictionaries
        """
        if not self.available:
            return []

        if (time.time() - self._last_interaction_time) < 2.0:
            self._element_cache.clear()

        cache_key = f"{app_name.lower()}:{interactive_only}"
        if use_cache and cache_key in self._element_cache:
            return self._element_cache[cache_key]

        app = self.get_app(app_name)
        if not app:
            return []

        elements: List[Dict[str, Any]] = []

        if hasattr(app, "AXMenuBar"):
            try:
                self._traverse(app.AXMenuBar, elements, interactive_only)
            except Exception:
                pass

        for window in self.get_windows(app):
            self._traverse(window, elements, interactive_only)

        self._element_cache[cache_key] = elements
        return elements

    def _traverse(
        self,
        node: Any,
        elements: List[Dict[str, Any]],
        interactive_only: bool,
        depth: int = 0,
    ) -> None:
        """Recursively traverse accessibility tree collecting elements."""
        if depth > 40:
            return

        try:
            role = str(getattr(node, "AXRole", ""))

            if role == "AXApplication":
                if hasattr(node, "AXChildren") and node.AXChildren:
                    for child in node.AXChildren:
                        self._traverse(child, elements, interactive_only, depth + 1)
                return

            has_actions = bool(hasattr(node, "AXActions") and node.AXActions)
            is_enabled = bool(hasattr(node, "AXEnabled") and node.AXEnabled)
            is_interactive = has_actions or is_enabled

            if not interactive_only or is_interactive:
                info = self._extract_element_info(node, role, has_actions, is_enabled)
                if info:
                    elements.append(info)

            if hasattr(node, "AXChildren") and node.AXChildren:
                for child in node.AXChildren:
                    self._traverse(child, elements, interactive_only, depth + 1)

        except Exception:
            pass

    def _extract_element_info(
        self, node: Any, role: str, has_actions: bool, is_enabled: bool
    ) -> Optional[Dict[str, Any]]:
        """Extract element info and register with unique ID."""
        try:
            if not (hasattr(node, "AXPosition") and hasattr(node, "AXSize")):
                return None

            pos = node.AXPosition
            size = node.AXSize
            x, y, w, h = pos[0], pos[1], size[0], size[1]

            if w <= 0 or h <= 0:
                return None
            if x < 0 or y < 0 or x > self.screen_width or y > self.screen_height:
                return None

            label = self._get_label(node)
            identifier = getattr(node, "AXIdentifier", "") or ""

            if not label and not identifier and not has_actions:
                return None

            element_id = str(uuid.uuid4())[:8]

            info = {
                "element_id": element_id,
                "identifier": identifier,
                "role": role.replace("AX", ""),
                "label": label,
                "title": label,
                "description": label,
                "center": [int(x + w / 2), int(y + h / 2)],
                "bounds": [int(x), int(y), int(w), int(h)],
                "has_actions": has_actions,
                "enabled": is_enabled,
                "_element": node,
            }

            self._element_registry[element_id] = info
            return info

        except Exception:
            return None

    def _get_label(self, node: Any) -> str:
        """Get the best available label for an element."""
        if hasattr(node, "AXAttributedDescription"):
            try:
                desc = str(node.AXAttributedDescription).split("{")[0].strip()
                if desc:
                    return desc
            except Exception:
                pass

        for attr in ("AXTitle", "AXValue", "AXDescription"):
            val = getattr(node, attr, None)
            if val:
                return str(val)

        return ""

    def get_element_by_id(self, element_id: str) -> Optional[Dict[str, Any]]:
        """Get element from registry by ID."""
        return self._element_registry.get(element_id)

    def click_by_id(self, element_id: str) -> Tuple[bool, str]:
        """
        Click element by its unique ID.

        Tries: coordinate click → parent click → native Press action.

        Args:
            element_id: Element ID from get_elements()

        Returns:
            (success, message)
        """
        if not self.available:
            return (False, "Accessibility not available")

        element = self._element_registry.get(element_id)
        if not element:
            return (False, f"Element ID '{element_id}' not found")

        node = element.get("_element")
        label = element.get("label", element_id)
        center = element.get("center")
        role = element.get("role", "")

        if role in ("StaticText", "Text") and node:
            parent = self._find_clickable_parent(node)
            if parent:
                result = self._click_node(parent, label)
                if result[0]:
                    return result

        if center and len(center) == 2:
            try:
                import pyautogui

                pyautogui.click(center[0], center[1])
                time.sleep(0.15)
                self.invalidate_cache()
                return (True, f"Clicked '{label}' at {tuple(center)}")
            except Exception:
                pass

        if node:
            return self._click_node(node, label)

        return (False, f"No click method for '{label}'")

    def _click_node(self, node: Any, label: str) -> Tuple[bool, str]:
        """Click a node using available methods."""
        try:
            if hasattr(node, "Press"):
                node.Press()
                time.sleep(0.1)
                self.invalidate_cache()
                return (True, f"Clicked '{label}' via Press")

            if hasattr(node, "AXPress"):
                node.AXPress()
                time.sleep(0.1)
                self.invalidate_cache()
                return (True, f"Clicked '{label}' via AXPress")

            if hasattr(node, "AXActions") and node.AXActions:
                for action in node.AXActions:
                    action_lower = str(action).lower()
                    if "press" in action_lower or "click" in action_lower:
                        if hasattr(node, "performAction"):
                            node.performAction(action)
                            time.sleep(0.1)
                            self.invalidate_cache()
                            return (True, f"Clicked '{label}' via {action}")

            if hasattr(node, "AXPosition") and hasattr(node, "AXSize"):
                pos = node.AXPosition
                size = node.AXSize
                x = int(pos[0] + size[0] / 2)
                y = int(pos[1] + size[1] / 2)
                import pyautogui

                pyautogui.click(x, y)
                time.sleep(0.15)
                self.invalidate_cache()
                return (True, f"Clicked '{label}' at ({x}, {y})")

        except Exception as e:
            return (False, f"Click failed: {e}")

        return (False, f"No click method for '{label}'")

    def _find_clickable_parent(self, node: Any, max_depth: int = 5) -> Optional[Any]:
        """Find a clickable ancestor element."""
        clickable_roles = {
            "AXRow",
            "AXOutlineRow",
            "AXCell",
            "AXButton",
            "AXMenuItem",
            "AXCheckBox",
            "AXRadioButton",
            "AXPopUpButton",
            "AXGroup",
        }

        try:
            current = node
            for _ in range(max_depth):
                if not hasattr(current, "AXParent") or not current.AXParent:
                    break
                current = current.AXParent
                role = str(getattr(current, "AXRole", ""))

                if role in clickable_roles:
                    if (
                        hasattr(current, "Press")
                        or hasattr(current, "AXPress")
                        or (hasattr(current, "AXActions") and current.AXActions)
                    ):
                        return current
        except Exception:
            pass

        return None

    def find_element(
        self, app_name: str, label: str, exact_match: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Find first element matching label."""
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

    def click_element(self, label: str, app_name: str) -> Tuple[bool, Optional[Dict]]:
        """Find and click element by label."""
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

    def click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> Tuple[bool, str]:
        """Try clicking element, fall back to parents if needed."""
        if not self.available:
            return (False, "unavailable")

        node = element_dict.get("_element")
        if not node:
            return (False, "no_reference")

        label = element_dict.get("label", "element")
        result = self._click_node(node, label)
        if result[0]:
            return (True, "element")

        current = node
        for depth in range(1, max_depth + 1):
            try:
                if hasattr(current, "AXParent") and current.AXParent:
                    parent = current.AXParent
                    result = self._click_node(parent, label)
                    if result[0]:
                        return (True, f"parent_{depth}")
                    current = parent
                else:
                    break
            except Exception:
                break

        return (False, "not_clickable")

    def get_text(self, app_name: str) -> List[str]:
        """Extract all text values from an application."""
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

    def get_window_bounds(self, app_name: str) -> Optional[Tuple[int, int, int, int]]:
        """Get bounds of the app's main window."""
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

    def is_app_running(self, app_name: str) -> bool:
        """Check if an application is running."""
        return self.get_app(app_name) is not None

    def get_running_apps(self) -> List[str]:
        """Get names of all running applications using localizedName."""
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

    def get_frontmost_app(self) -> Optional[str]:
        """Get name of the frontmost application."""
        if not self.available:
            return None

        try:
            app = self.atomacos.getFrontmostApp()
            if app:
                return getattr(app, "AXTitle", None)
        except Exception:
            pass

        return None

    def is_app_frontmost(self, app_name: str) -> bool:
        """Check if an application is frontmost."""
        frontmost = self.get_frontmost_app()
        return frontmost is not None and self._matches_name(frontmost, app_name)

    def _matches_name(self, name1: str, name2: str) -> bool:
        """Case-insensitive partial name matching."""
        if not name1 or not name2:
            return False
        n1, n2 = name1.lower(), name2.lower()
        return n1 in n2 or n2 in n1

    def get_all_ui_elements(
        self, app_name: Optional[str] = None, include_menu_bar: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get all UI elements categorized by type."""
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
        """Get all interactive elements."""
        if not app_name:
            return []
        return self.get_elements(app_name, interactive_only=True)

    def find_elements(
        self,
        label: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find elements by label and/or role."""
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

    def try_click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> Tuple[bool, str]:
        """Alias for click_element_or_parent."""
        return self.click_element_or_parent(element_dict, max_depth)

    def get_text_from_app(self, app_name: str, role: Optional[str] = None) -> List[str]:
        """Alias for get_text."""
        return self.get_text(app_name)

    def get_app_window_bounds(
        self, app_name: Optional[str] = None
    ) -> Optional[Tuple[int, int, int, int]]:
        """Alias for get_window_bounds."""
        if not app_name:
            return None
        return self.get_window_bounds(app_name)

    def get_running_app_names(self) -> List[str]:
        """Alias for get_running_apps."""
        return self.get_running_apps()

    def get_frontmost_app_name(self) -> Optional[str]:
        """Alias for get_frontmost_app."""
        return self.get_frontmost_app()

    def clear_app_cache(self) -> None:
        """Alias for clear_cache."""
        self.clear_cache()
