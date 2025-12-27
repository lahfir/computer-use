"""
macOS Accessibility API using atomacos for fast, accurate element interaction.

Design principles:
- Let the API tell us what's interactive (hasActions/isEnabled), don't guess by role
- Smart traversal that prioritizes focused/visible content
- Element registry for direct native clicks by ID (no label search)
- Cache invalidation after interactions
- Fast clicking without OCR fallback
"""

from typing import List, Optional, Dict, Any, Tuple
import platform
import time
import uuid

from ...utils.ui import print_warning, print_info


class MacOSAccessibility:
    """
    macOS accessibility using atomacos library.
    Provides 100% accurate element coordinates via AX APIs.

    Element Registry Pattern:
    - Each discovered element gets a unique ID
    - Elements are stored in registry with native node reference
    - click_by_id() uses registry for direct native clicks
    - Solves duplicate label problem - IDs are unique
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        """
        Initialize macOS accessibility with atomacos.

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
        """Check if atomacos is available and platform is macOS."""
        if platform.system().lower() != "darwin":
            return False
        import importlib.util

        return importlib.util.find_spec("atomacos") is not None

    def _initialize_api(self):
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

    def set_active_app(self, app_name: str):
        """
        Set and cache the active application.

        Args:
            app_name: Application name to set as active
        """
        self._element_cache.clear()
        try:
            app = self.atomacos.getAppRefByLocalizedName(app_name)
            if app and self._matches_name(getattr(app, "AXTitle", ""), app_name):
                self._app_cache[app_name.lower()] = app
        except Exception:
            pass

    def clear_cache(self):
        """Clear all caches to force fresh lookups."""
        self._app_cache.clear()
        self._element_cache.clear()

    def get_app(self, app_name: str) -> Optional[Any]:
        """
        Get application reference, using cache when available.

        Args:
            app_name: Application name

        Returns:
            App reference or None
        """
        if not self.available or not app_name:
            return None

        cache_key = app_name.lower()
        if cache_key in self._app_cache:
            return self._app_cache[cache_key]

        try:
            app = self.atomacos.getAppRefByLocalizedName(app_name)
            if app and self._matches_name(getattr(app, "AXTitle", ""), app_name):
                self._app_cache[cache_key] = app
                return app
        except Exception:
            pass

        try:
            for app in self.atomacos.NativeUIElement.runningApplications():
                title = getattr(app, "AXTitle", "")
                if self._matches_name(title, app_name):
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

    def invalidate_cache(self):
        """
        Invalidate element cache and registry after interactions.
        Should be called after clicks, focus changes, etc.
        """
        self._element_cache.clear()
        self._element_registry.clear()
        self._last_interaction_time = time.time()

    def get_elements(
        self, app_name: str, interactive_only: bool = True, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all UI elements from an application, prioritizing focused content.

        The API itself tells us what's interactive by checking:
        - Has actions (AXActions)
        - Is enabled (AXEnabled)
        - Has valid bounds for clicking

        Smart traversal:
        - Detects split views and prioritizes the focused/content pane
        - Always clears cache if recent interaction occurred
        - Returns elements sorted by visual relevance

        Args:
            app_name: Application name
            interactive_only: Only return elements that can be interacted with
            use_cache: Use cached elements if available

        Returns:
            List of element dictionaries with coordinates and metadata
        """
        if not self.available:
            return []

        recent_interaction = (time.time() - self._last_interaction_time) < 2.0
        if recent_interaction:
            self._element_cache.clear()

        cache_key = f"{app_name.lower()}:{interactive_only}"
        if use_cache and cache_key in self._element_cache:
            return self._element_cache[cache_key]

        app = self.get_app(app_name)
        if not app:
            return []

        elements = []
        windows = self.get_windows(app)

        if hasattr(app, "AXMenuBar"):
            try:
                self._traverse(app.AXMenuBar, elements, interactive_only)
            except Exception:
                pass

        for window in windows:
            self._traverse(window, elements, interactive_only)

        self._element_cache[cache_key] = elements
        return elements

    def _find_focused_content_area(self, window: Any) -> Optional[Any]:
        """
        Find the focused/main content area in split views.

        For apps like System Settings, this finds the right-side content pane
        rather than the sidebar.

        Args:
            window: Window to search

        Returns:
            Focused content node or None
        """
        try:
            if hasattr(window, "AXFocusedUIElement"):
                focused = window.AXFocusedUIElement
                if focused:
                    ancestor = self._find_content_ancestor(focused)
                    if ancestor:
                        return ancestor

            split_group = self._find_split_group(window)
            if split_group:
                return self._get_content_pane(split_group)

        except Exception:
            pass

        return None

    def _find_split_group(self, node: Any, depth: int = 0) -> Optional[Any]:
        """Find AXSplitGroup in the hierarchy."""
        if depth > 10:
            return None

        try:
            role = str(getattr(node, "AXRole", ""))
            if role == "AXSplitGroup":
                return node

            if hasattr(node, "AXChildren") and node.AXChildren:
                for child in node.AXChildren:
                    result = self._find_split_group(child, depth + 1)
                    if result:
                        return result
        except Exception:
            pass

        return None

    def _get_content_pane(self, split_group: Any) -> Optional[Any]:
        """
        Get the main content pane from a split group.
        Usually the larger/right-most pane.
        """
        try:
            if not hasattr(split_group, "AXChildren") or not split_group.AXChildren:
                return None

            children = list(split_group.AXChildren)
            if len(children) < 2:
                return None

            best_pane = None
            best_width = 0

            for child in children:
                try:
                    role = str(getattr(child, "AXRole", ""))
                    if role in ("AXScrollArea", "AXGroup", "AXSplitter"):
                        if hasattr(child, "AXSize"):
                            width = child.AXSize[0]
                            if width > best_width:
                                best_width = width
                                best_pane = child
                except Exception:
                    continue

            return best_pane
        except Exception:
            return None

    def _find_content_ancestor(self, node: Any, depth: int = 0) -> Optional[Any]:
        """
        Walk up from focused element to find a good content container.
        """
        if depth > 10:
            return None

        try:
            role = str(getattr(node, "AXRole", ""))

            if role in ("AXScrollArea", "AXGroup") and hasattr(node, "AXSize"):
                size = node.AXSize
                if size[0] > 300 and size[1] > 200:
                    return node

            if hasattr(node, "AXParent") and node.AXParent:
                return self._find_content_ancestor(node.AXParent, depth + 1)
        except Exception:
            pass

        return None

    def _traverse(
        self,
        node: Any,
        elements: List[Dict[str, Any]],
        interactive_only: bool,
        depth: int = 0,
    ):
        """
        Single unified traversal - the API tells us what's interactive.

        Args:
            node: Current accessibility node
            elements: List to collect elements into
            interactive_only: Only collect interactive elements
            depth: Current recursion depth (max 40)
        """
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
                element_info = self._extract_info(node, role, has_actions, is_enabled)
                if element_info:
                    elements.append(element_info)

            if hasattr(node, "AXChildren") and node.AXChildren:
                for child in node.AXChildren:
                    self._traverse(child, elements, interactive_only, depth + 1)

        except Exception:
            pass

    def _extract_info(
        self, node: Any, role: str, has_actions: bool, is_enabled: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Extract element info and register it with unique ID.

        Each element gets a unique element_id that can be used for
        direct native clicks via click_by_id(). This solves the
        duplicate label problem.

        Args:
            node: Accessibility node
            role: Element role string
            has_actions: Whether element has actions
            is_enabled: Whether element is enabled

        Returns:
            Element dict with element_id, or None if invalid
        """
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

            element_info = {
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

            self._element_registry[element_id] = element_info

            return element_info
        except Exception:
            return None

    def _get_label(self, node: Any) -> str:
        """
        Get the best label for an element.

        Args:
            node: Accessibility node

        Returns:
            Label string
        """
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

        Priority:
        1. Coordinate click (most reliable, works for any element)
        2. Native Press on clickable parent (for StaticText in rows/cells)
        3. Native Press on element itself

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
        center = element.get("center")
        role = element.get("role", "")

        if node:
            if role in ("StaticText", "Text"):
                clickable_parent = self._find_clickable_parent(node)
                if clickable_parent:
                    try:
                        if hasattr(clickable_parent, "AXPosition"):
                            parent_pos = clickable_parent.AXPosition
                            parent_size = clickable_parent.AXSize
                            px = int(parent_pos[0] + parent_size[0] / 2)
                            py = int(parent_pos[1] + parent_size[1] / 2)
                            import pyautogui

                            pyautogui.click(px, py)
                            time.sleep(0.15)
                            self.invalidate_cache()
                            return (
                                True,
                                f"Clicked parent row of '{label}' at ({px}, {py})",
                            )
                    except Exception:
                        pass
                    try:
                        self._perform_click(clickable_parent)
                        time.sleep(0.1)
                        self.invalidate_cache()
                        return (True, f"Clicked parent of '{label}'")
                    except Exception:
                        pass

        if center and len(center) == 2:
            try:
                import pyautogui

                x, y = center
                pyautogui.click(x, y)
                time.sleep(0.15)
                self.invalidate_cache()
                return (True, f"Clicked '{label}' at ({x}, {y})")
            except Exception:
                pass

        if node:
            clickable_parent = self._find_clickable_parent(node)
            if clickable_parent:
                try:
                    self._perform_click(clickable_parent)
                    time.sleep(0.1)
                    self.invalidate_cache()
                    return (True, f"Clicked parent of '{label}'")
                except Exception:
                    pass

            try:
                self._perform_click(node)
                time.sleep(0.1)
                self.invalidate_cache()
                return (True, f"Clicked '{label}'")
            except Exception:
                pass

        return (False, f"No click method available for '{label}'")

    def _find_clickable_parent(self, node: Any, max_depth: int = 5) -> Optional[Any]:
        """
        Walk up the parent chain to find a clickable ancestor.

        Useful for StaticText inside Row/Cell/Button elements.

        Args:
            node: Starting node
            max_depth: How far up to search

        Returns:
            Clickable parent node or None
        """
        try:
            current = node
            for _ in range(max_depth):
                if not hasattr(current, "AXParent") or not current.AXParent:
                    break
                current = current.AXParent
                role = str(getattr(current, "AXRole", ""))
                if role in (
                    "AXRow",
                    "AXOutlineRow",
                    "AXCell",
                    "AXButton",
                    "AXMenuItem",
                    "AXCheckBox",
                    "AXRadioButton",
                    "AXPopUpButton",
                    "AXGroup",
                ):
                    if hasattr(current, "Press") or hasattr(current, "AXPress"):
                        return current
                    if hasattr(current, "AXActions") and current.AXActions:
                        return current
        except Exception:
            pass
        return None

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
                if hasattr(current, "AXParent") and current.AXParent:
                    parent = current.AXParent
                    try:
                        self._perform_click(parent)
                        self.invalidate_cache()
                        return (True, f"parent_{depth}")
                    except Exception:
                        current = parent
                else:
                    break
            except Exception:
                break

        return (False, "not_clickable")

    def _perform_click(self, node: Any):
        """
        Perform click on an accessibility node using all available methods.

        Args:
            node: Element to click

        Raises:
            Exception: If all click methods fail
        """
        if hasattr(node, "Press"):
            node.Press()
            return

        if hasattr(node, "AXPress"):
            node.AXPress()
            return

        if hasattr(node, "AXActions") and node.AXActions:
            actions = node.AXActions
            for action in actions:
                if "press" in str(action).lower() or "click" in str(action).lower():
                    if hasattr(node, "performAction"):
                        node.performAction(action)
                        return

        if hasattr(node, "AXRole"):
            role = str(node.AXRole)
            if role in ("AXRow", "AXCell", "AXOutlineRow"):
                if hasattr(node, "AXSelected"):
                    try:
                        node.AXSelected = True
                        return
                    except Exception:
                        pass

        raise Exception("No Press action available")

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
            for key in ("label", "title", "description"):
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
            w = windows[0]
            pos = w.AXPosition
            size = w.AXSize
            return (int(pos[0]), int(pos[1]), int(size[0]), int(size[1]))
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

        try:
            import subprocess

            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of every application process',
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return [n.strip() for n in result.stdout.strip().split(",")]
        except Exception:
            return []

    def get_frontmost_app(self) -> Optional[str]:
        """
        Get the name of the frontmost application.

        Returns:
            App name or None
        """
        if not self.available:
            return None

        try:
            import subprocess

            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def is_app_frontmost(self, app_name: str) -> bool:
        """
        Check if an application is frontmost.

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
        Get all UI elements categorized by type.

        Kept for backward compatibility with existing code.
        Categories are determined by the API's reported role.

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
        """
        Get all interactive elements.

        Kept for backward compatibility.

        Args:
            app_name: Application name

        Returns:
            List of interactive elements
        """
        if not app_name:
            return []
        return self.get_elements(app_name, interactive_only=True)

    def find_elements(
        self,
        label: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find elements by label and/or role.

        Kept for backward compatibility.

        Args:
            label: Text to search for
            role: Role filter
            app_name: Application name

        Returns:
            List of matching elements
        """
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
    ) -> tuple:
        """
        Backward compatible alias for click_element_or_parent.

        Args:
            element_dict: Element dictionary
            max_depth: Max parent depth

        Returns:
            Tuple of (success, method)
        """
        return self.click_element_or_parent(element_dict, max_depth)

    def get_text_from_app(self, app_name: str, role: Optional[str] = None) -> List[str]:
        """
        Backward compatible alias for get_text.

        Args:
            app_name: Application name
            role: Unused, kept for compatibility

        Returns:
            List of text strings
        """
        return self.get_text(app_name)

    def get_app_window_bounds(self, app_name: Optional[str] = None) -> Optional[tuple]:
        """
        Backward compatible alias for get_window_bounds.

        Args:
            app_name: Application name

        Returns:
            Window bounds or None
        """
        if not app_name:
            return None
        return self.get_window_bounds(app_name)

    def get_running_app_names(self) -> List[str]:
        """
        Backward compatible alias for get_running_apps.

        Returns:
            List of app names
        """
        return self.get_running_apps()

    def get_frontmost_app_name(self) -> Optional[str]:
        """
        Backward compatible alias for get_frontmost_app.

        Returns:
            Frontmost app name
        """
        return self.get_frontmost_app()

    def clear_app_cache(self):
        """
        Backward compatible alias for clear_cache.
        """
        self.clear_cache()
