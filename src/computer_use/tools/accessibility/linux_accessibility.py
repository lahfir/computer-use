"""
Linux AT-SPI accessibility API using pyatspi for fast, accurate element interaction.

Design principles:
- Let the API tell us what's interactive (has actions/is enabled), don't guess by role
- Element registry for direct native clicks by ID (no label search)
- Cache invalidation after interactions
- Fast clicking without OCR fallback
"""

from typing import List, Optional, Dict, Any, Tuple
import platform
import time
import uuid

from ...utils.ui import print_warning, print_info


class LinuxAccessibility:
    """
    Linux AT-SPI using pyatspi library.
    Provides 100% accurate element coordinates via AT-SPI APIs.

    Element Registry Pattern:
    - Each discovered element gets a unique ID
    - Elements are stored in registry with native node reference
    - click_by_id() uses registry for direct native clicks
    """

    _CACHE_TTL: float = 30.0

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        """
        Initialize Linux AT-SPI with pyatspi.

        Args:
            screen_width: Screen width for bounds validation
            screen_height: Screen height for bounds validation
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.available = self._check_availability()
        self.pyatspi = None
        self.desktop = None
        self._app_cache: Dict[str, Any] = {}
        self._element_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._element_registry: Dict[str, Dict[str, Any]] = {}
        self._last_interaction_time: float = 0

        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        """Check if pyatspi is available and platform is Linux."""
        if platform.system().lower() != "linux":
            return False
        import importlib.util

        return importlib.util.find_spec("pyatspi") is not None

    def _initialize_api(self):
        """Initialize pyatspi and verify AT-SPI permissions."""
        try:
            import pyatspi

            self.pyatspi = pyatspi
            self.desktop = pyatspi.Registry.getDesktop(0)
            list(self.desktop)
            from ...utils.ui import print_verbose_only

            print_verbose_only("✓ Accessibility API ready")
        except Exception as e:
            print_warning(f"AT-SPI not available: {e}")
            print_info("Ensure accessibility is enabled in system settings")
            self.available = False

    def set_active_app(self, app_name: str):
        """
        Set and cache the active application.

        Args:
            app_name: Application name to set as active
        """
        self.invalidate_cache(app_name)
        app = self.get_app(app_name)
        if app:
            self._app_cache[app_name.lower()] = app

    def clear_cache(self):
        """Clear all caches to force fresh lookups."""
        self._app_cache.clear()
        self._element_cache.clear()

    def invalidate_cache(self, app_name: Optional[str] = None):
        """
        Invalidate element cache after interactions.

        Args:
            app_name: If provided, only invalidate cache for this app
        """
        if app_name:
            prefix = app_name.lower()
            keys_to_remove = [k for k in self._element_cache if k.startswith(prefix)]
            for key in keys_to_remove:
                self._element_cache.pop(key, None)
            registry_keys = [k for k in self._element_registry if k.startswith(prefix)]
            for key in registry_keys:
                self._element_registry.pop(key, None)
        else:
            self._element_cache.clear()
            self._element_registry.clear()
        self._last_interaction_time = time.time()

    def get_app(self, app_name: str, retry_count: int = 3) -> Optional[Any]:
        """
        Get application reference, using cache when available.

        Args:
            app_name: Application name
            retry_count: Number of retry attempts (for API consistency)

        Returns:
            App reference or None
        """
        if not self.available or not app_name:
            return None

        cache_key = app_name.lower()
        if cache_key in self._app_cache:
            return self._app_cache[cache_key]

        try:
            for app in self.desktop:
                name = getattr(app, "name", "")
                if name and self._matches_name(name, app_name):
                    self._app_cache[cache_key] = app
                    return app
        except Exception:
            pass

        return None

    def get_windows(self, app: Any) -> List[Any]:
        """
        Get all windows for an application.

        Args:
            app: Application reference

        Returns:
            List of window references
        """
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
        """
        Get all UI elements from an application.

        The API itself tells us what's interactive by checking:
        - Has actions (queryAction)
        - Is enabled (STATE_ENABLED)
        - Has valid bounds for clicking

        Args:
            app_name: Application name
            interactive_only: Only return elements that can be interacted with
            use_cache: Use cached elements if available (TTL-based, 2s default)

        Returns:
            List of element dictionaries with coordinates and metadata
        """
        if not self.available:
            return []

        cache_key = f"{app_name.lower()}:{interactive_only}"

        if use_cache and cache_key in self._element_cache:
            cached_time, cached_elements = self._element_cache[cache_key]
            if (time.time() - cached_time) < self._CACHE_TTL:
                return cached_elements

        app = self.get_app(app_name)
        if not app:
            return []

        elements: List[Dict[str, Any]] = []
        app_name_lower = app_name.lower()
        for window in self.get_windows(app):
            self._traverse(window, elements, interactive_only, 0, app_name_lower)

        self._element_cache[cache_key] = (time.time(), elements)
        return elements

    def _traverse(
        self,
        node: Any,
        elements: List[Dict[str, Any]],
        interactive_only: bool,
        depth: int = 0,
        app_name: str = "",
    ):
        """
        Single unified traversal - the API tells us what's interactive.

        Args:
            node: Current AT-SPI node
            elements: List to collect elements into
            interactive_only: Only collect interactive elements
            depth: Current recursion depth (max 25)
        """
        if depth > 25:
            return

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

            is_interactive = has_actions or is_enabled

            if not interactive_only or is_interactive:
                element_info = self._extract_info(
                    node, has_actions, is_enabled, app_name
                )
                if element_info:
                    elements.append(element_info)

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

    def _extract_info(
        self, node: Any, has_actions: bool, is_enabled: bool, app_name: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Extract element info and register it with unique ID.

        Args:
            node: AT-SPI node
            has_actions: Whether element has actions
            is_enabled: Whether element is enabled
            app_name: Application name for selective cache invalidation

        Returns:
            Element dict with element_id, or None if invalid
        """
        try:
            component = node.queryComponent()
            extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)
            x, y, w, h = extents

            if w <= 0 or h <= 0:
                return None
            if x < 0 or y < 0 or x > self.screen_width or y > self.screen_height:
                return None

            name = getattr(node, "name", "") or ""
            description = getattr(node, "description", "") or ""
            label = description or name

            if not label and not name:
                return None

            role = node.getRoleName() if hasattr(node, "getRoleName") else ""

            element_id = str(uuid.uuid4())[:8]

            element_info = {
                "element_id": element_id,
                "identifier": name,
                "role": role,
                "label": label,
                "title": label,
                "description": description,
                "center": [int(x + w / 2), int(y + h / 2)],
                "bounds": [int(x), int(y), int(w), int(h)],
                "has_actions": has_actions,
                "enabled": is_enabled,
                "_element": node,
                "_app_name": app_name,
            }

            self._element_registry[element_id] = element_info

            return element_info
        except Exception:
            return None

    def get_element_by_id(self, element_id: str) -> Optional[Dict[str, Any]]:
        """
        Get element from registry by its unique ID.

        Args:
            element_id: Unique element ID from get_elements()

        Returns:
            Element dict with _element reference, or None
        """
        return self._element_registry.get(element_id)

    def click_by_id(self, element_id: str) -> Tuple[bool, str]:
        """
        Click element directly using its unique ID.
        Falls back to coordinate click if native action unavailable.

        Args:
            element_id: Unique element ID from get_elements()

        Returns:
            Tuple of (success, message)
        """
        if not self.available:
            return (False, "Accessibility not available")

        element = self._element_registry.get(element_id)
        if not element:
            return (False, f"Element ID '{element_id}' not found in registry")

        node = element.get("_element")
        label = element.get("label", element_id)
        app_name = element.get("_app_name", "")
        invalidate_target = app_name if app_name else None

        if node:
            try:
                self._perform_click(node)
                self.invalidate_cache(invalidate_target)
                return (True, f"Clicked '{label}'")
            except Exception:
                pass

        center = element.get("center")
        if center and len(center) == 2:
            try:
                import pyautogui

                x, y = center
                pyautogui.click(x, y)
                self.invalidate_cache(invalidate_target)
                return (True, f"Clicked '{label}' at ({x}, {y})")
            except Exception as e:
                return (False, f"Coordinate click failed: {e}")

        return (False, f"No click method available for '{label}'")

    def find_element(
        self, app_name: str, label: str, exact_match: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Find first element matching label.

        Args:
            app_name: Application name
            label: Text to search for
            exact_match: Require exact match vs contains

        Returns:
            Element dict or None
        """
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

    def click_element(self, label: str, app_name: str) -> tuple:
        """
        Find and click element by label.

        Args:
            label: Element label to find
            app_name: Application name

        Returns:
            Tuple of (success, element)
        """
        if not self.available:
            return (False, None)

        element = self.find_element(app_name, label)
        if not element:
            return (False, None)

        node = element.get("_element")
        if not node:
            return (False, element)

        try:
            self._perform_click(node)
            self.invalidate_cache()
            return (True, element)
        except Exception:
            return (False, element)

    def click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> tuple:
        """
        Try clicking element, fall back to parents if needed.

        Args:
            element_dict: Element dictionary with _element reference
            max_depth: How many parents to try

        Returns:
            Tuple of (success, method)
        """
        if not self.available:
            return (False, "unavailable")

        node = element_dict.get("_element")
        if not node:
            return (False, "no_reference")

        try:
            self._perform_click(node)
            self.invalidate_cache()
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
                            self.invalidate_cache()
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

    def _perform_click(self, node: Any):
        """
        Perform click on an AT-SPI node.

        Args:
            node: Element to click

        Raises:
            Exception: If click fails
        """
        action_iface = node.queryAction()
        for i in range(action_iface.nActions):
            action_name = action_iface.getName(i).lower()
            if "click" in action_name or "press" in action_name:
                action_iface.doAction(i)
                return
        raise Exception("No click/press action available")

    def get_text(self, app_name: str) -> List[str]:
        """
        Extract all text values from an application.

        Args:
            app_name: Application name

        Returns:
            List of text strings
        """
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

    def get_window_bounds(self, app_name: str) -> Optional[tuple]:
        """
        Get the bounds of the app's main window.

        Args:
            app_name: Application name

        Returns:
            (x, y, width, height) or None
        """
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
            x, y, w, h = extents
            return (int(x), int(y), int(w), int(h))
        except Exception:
            return None

    def is_app_running(self, app_name: str) -> bool:
        """
        Check if an application is running.

        Args:
            app_name: Application name

        Returns:
            True if running
        """
        return self.get_app(app_name) is not None

    def get_running_apps(self) -> List[str]:
        """
        Get names of all running applications.

        Returns:
            List of app names
        """
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

    def get_frontmost_app(self) -> Optional[str]:
        """
        Get the name of the application with an active window.

        Returns:
            App name or None
        """
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
        """
        Check if an application has an active window.

        Args:
            app_name: Application name

        Returns:
            True if frontmost
        """
        frontmost = self.get_frontmost_app()
        return frontmost is not None and self._matches_name(frontmost, app_name)

    def _matches_name(self, name1: str, name2: str) -> bool:
        """
        Check if two names match (case-insensitive, partial).

        Args:
            name1: First name
            name2: Second name

        Returns:
            True if names match
        """
        if not name1 or not name2:
            return False
        n1, n2 = name1.lower(), name2.lower()
        return n1 in n2 or n2 in n1

    def get_all_ui_elements(
        self, app_name: Optional[str] = None, include_menu_bar: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all UI elements categorized by type (backward compatible).

        Args:
            app_name: Application name
            include_menu_bar: Include menu bar elements

        Returns:
            Dict with categorized elements
        """
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
        """Get all interactive elements (backward compatible)."""
        if not app_name:
            return []
        return self.get_elements(app_name, interactive_only=True)

    def find_elements(
        self,
        label: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find elements by label and/or role (backward compatible)."""
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

    def try_click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> tuple:
        """Backward compatible alias."""
        return self.click_element_or_parent(element_dict, max_depth)

    def get_text_from_app(self, app_name: str, role: Optional[str] = None) -> List[str]:
        """Backward compatible alias."""
        return self.get_text(app_name)

    def get_app_window_bounds(self, app_name: Optional[str] = None) -> Optional[tuple]:
        """Backward compatible alias."""
        if not app_name:
            return None
        return self.get_window_bounds(app_name)

    def get_running_app_names(self) -> List[str]:
        """Backward compatible alias."""
        return self.get_running_apps()

    def get_frontmost_app_name(self) -> Optional[str]:
        """Backward compatible alias."""
        return self.get_frontmost_app()

    def clear_app_cache(self):
        """Backward compatible alias."""
        self.clear_cache()
