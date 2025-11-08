"""
Linux AT-SPI accessibility API using pyatspi for 100% accurate element interaction.
"""

from typing import List, Optional, Dict, Any
import platform

from ...utils.ui import print_success, print_warning, print_info, console
from ...config.timing_config import get_timing_config


class LinuxAccessibility:
    """
    Linux AT-SPI using pyatspi library.
    Provides 100% accurate element coordinates and direct interaction via AT-SPI APIs.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        """Initialize Linux AT-SPI with pyatspi."""
        self.available = self._check_availability()
        self.current_app_name = None
        self.current_app_ref = None
        self.screen_width = screen_width
        self.screen_height = screen_height
        if self.available:
            self._initialize_api()

    def set_active_app(self, app_name: str):
        """
        Set the active app that's currently in focus.

        This should be called by open_application after successfully focusing the app.
        The cached reference will be used for all subsequent operations until a different app is opened.

        Args:
            app_name: The application name that was just opened/focused
        """
        print(f"        [set_active_app] Setting active app to '{app_name}'")

        if self.current_app_name and self.current_app_name.lower() != app_name.lower():
            print(
                f"        [set_active_app] Switching from '{self.current_app_name}' to '{app_name}'"
            )
            self.current_app_name = None
            self.current_app_ref = None

        try:
            app = self._get_app(app_name)
            if app and hasattr(app, "name"):
                app_title = app.name
                if app_title and (
                    app_name.lower() in app_title.lower()
                    or app_title.lower() in app_name.lower()
                ):
                    print(
                        f"        [set_active_app] ✅ Cached '{app_title}' as active app"
                    )
                    self.current_app_name = app_name
                    self.current_app_ref = app
                else:
                    print(
                        f"        [set_active_app] ❌ App name mismatch: requested '{app_name}', got '{app_title}'"
                    )
        except Exception as e:
            print(f"        [set_active_app] ⚠️  Failed to cache app: {e}")

    def clear_app_cache(self):
        """
        Clear the cached app reference.

        Use this only when you need to force a fresh lookup (e.g., on retries).
        """
        print("        [clear_app_cache] Clearing cached app reference")
        self.current_app_name = None
        self.current_app_ref = None

    def _check_availability(self) -> bool:
        """Check if pyatspi is available and platform is Linux."""
        if platform.system().lower() != "linux":
            return False

        try:
            import pyatspi  # noqa: F401

            return True
        except ImportError:
            return False

    def _initialize_api(self):
        """Initialize pyatspi and check AT-SPI permissions."""
        try:
            import pyatspi

            self.pyatspi = pyatspi
            self.desktop = pyatspi.Registry.getDesktop(0)

            try:
                list(self.desktop)
                print_success("Accessibility API ready with 100% accurate coordinates")
            except Exception:
                print_warning("AT-SPI permissions issue")
                print_info("Ensure accessibility is enabled in system settings")
                self.available = False

        except Exception as e:
            print_warning(f"Failed to initialize AT-SPI: {e}")
            self.available = False

    def click_element(self, label: str, app_name: Optional[str] = None) -> tuple:
        """
        Find and click element directly using AT-SPI API.

        Args:
            label: Text to search for in element
            app_name: Application name to search in

        Returns:
            Tuple of (success: bool, element: Optional[element])
        """
        if not self.available:
            return (False, None)

        try:
            app = self._get_app(app_name)
            if not app:
                return (False, None)

            element = self._find_element(app, label.lower())

            if element:
                from ...utils.ui import console, print_success, print_warning

                elem_name = getattr(element, "name", "N/A")
                console.print(f"    [dim]Found: {elem_name}[/dim]")

                try:
                    action_iface = element.queryAction()
                    for i in range(action_iface.nActions):
                        action_name = action_iface.getName(i)
                        if (
                            "click" in action_name.lower()
                            or "press" in action_name.lower()
                        ):
                            action_iface.doAction(i)
                            print_success(f"Clicked '{elem_name}' via AT-SPI")
                            return (True, element)

                    print_warning("No click action available")
                    return (False, element)
                except Exception as e:
                    print_warning(f"Native click failed: {e}")
                    return (False, element)

            return (False, None)

        except Exception as e:
            from ...utils.ui import print_warning

            print_warning(f"AT-SPI search failed: {e}")
            return (False, None)

    def try_click_element_or_parent(
        self, element_dict: Dict[str, Any], max_depth: int = 5
    ) -> tuple:
        """
        Try to click element using native accessibility, traversing up to parent if needed.

        Args:
            element_dict: Element dictionary with bounds, title, etc.
            max_depth: Maximum parent traversal depth

        Returns:
            Tuple of (success: bool, method: str)
            method can be: "element", "parent_N", or "failed"
        """
        if not self.available:
            return (False, "unavailable")

        try:
            element = element_dict.get("_element")
            if not element:
                return (False, "no_element_reference")

            console.print("    [dim]Trying native click on element...[/dim]")
            try:
                self._perform_click(element)
                console.print("    [green]✅ Clicked element directly![/green]")
                return (True, "element")
            except Exception as e:
                console.print(f"    [dim]Element click failed: {e}[/dim]")

            current = element
            for depth in range(1, max_depth + 1):
                try:
                    if hasattr(current, "getParent") and current.getParent():
                        parent = current.getParent()
                        parent_role = (
                            parent.getRoleName()
                            if hasattr(parent, "getRoleName")
                            else "Unknown"
                        )
                        console.print(
                            f"    [dim]Trying parent {depth} ({parent_role})...[/dim]"
                        )

                        try:
                            self._perform_click(parent)
                            console.print(
                                f"    [green]✅ Clicked parent {depth}![/green]"
                            )
                            return (True, f"parent_{depth}")
                        except Exception as e:
                            console.print(
                                f"    [dim]Parent {depth} click failed: {e}[/dim]"
                            )
                            current = parent
                    else:
                        break
                except Exception:
                    break

            return (False, "not_clickable")

        except Exception as e:
            console.print(f"    [yellow]Native click error: {e}[/yellow]")
            return (False, "error")

    def get_all_interactive_elements(
        self, app_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all interactive elements with their identifiers.

        Args:
            app_name: Application name to search in

        Returns:
            List of elements with identifier, role, and description
        """
        if not self.available:
            return []

        elements = []

        try:
            app = self._get_app(app_name)
            if not app:
                return []

            self._collect_interactive_elements(app, elements)

        except Exception:
            pass

        return elements

    def get_all_ui_elements(
        self, app_name: Optional[str] = None, include_menu_bar: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get ALL UI elements from an application with categorization.
        Includes interactive elements, menu items, toolbars, and more.

        Args:
            app_name: Application name to search in
            include_menu_bar: Whether to include menu bar items

        Returns:
            Dictionary with categorized elements:
            {
                "interactive": [...],  # Buttons, text fields, etc.
                "menu_bar": [...],     # Menu bar items
                "menu_items": [...],   # Menu items (File, Edit, etc.)
                "static": [...],       # Labels, static text
                "structural": [...]    # Groups, toolbars, containers
            }
        """
        if not self.available:
            return {
                "interactive": [],
                "menu_bar": [],
                "menu_items": [],
                "static": [],
                "structural": [],
            }

        categorized = {
            "interactive": [],
            "menu_bar": [],
            "menu_items": [],
            "static": [],
            "structural": [],
        }

        try:
            app = None
            windows = []

            print(f"🔍 Retry loop START for '{app_name}'")

            timing = get_timing_config()
            for attempt in range(timing.accessibility_retry_count):
                print(
                    f"    🔄 Attempt {attempt + 1}/{timing.accessibility_retry_count}: Getting fresh app reference..."
                )

                if attempt > 0:
                    print("        [RETRY] Clearing app cache to force fresh lookup...")
                    self.current_app_name = None
                    self.current_app_ref = None

                app = self._get_app(app_name)

                if app is None:
                    print(
                        f"    ❌ Attempt {attempt + 1}/{timing.accessibility_retry_count}: App reference is None!"
                    )
                    continue

                app_name_attr = getattr(app, "name", "Unknown")
                print(f"    ✓ Got app reference: {app_name_attr}")

                windows = self._get_app_windows(app)

                print(f"    📊 _get_app_windows returned {len(windows)} window(s)")

                if windows:
                    print(
                        f"    ✅ SUCCESS on attempt {attempt + 1}: {len(windows)} window(s)"
                    )
                    break
                else:
                    print(f"    ⚠️  Attempt {attempt + 1}/3: 0 windows!")

            if not app:
                print("    ❌ FAILED: No app reference after 3 attempts")
                return categorized

            if not windows:
                app_name_attr = getattr(app, "name", "Unknown")
                print(
                    f"    ❌ FAILED: App '{app_name_attr}' has 0 windows after 3 retries!"
                )

            print(
                f"    Searching {len(windows)} window(s) for all UI elements (categorized)"
            )

            for window in windows:
                self._collect_all_elements(
                    window, categorized, depth=0, context="window"
                )

            if all(len(v) == 0 for v in categorized.values()) and len(windows) > 0:
                frontmost = self.get_frontmost_app_name()
                if frontmost and frontmost.lower() != (app_name or "").lower():
                    print(f"    ⚠️  Frontmost app is '{frontmost}', trying that instead")
                    frontmost_app = self._get_app(frontmost)
                    if frontmost_app:
                        frontmost_windows = self._get_app_windows(frontmost_app)
                        for window in frontmost_windows:
                            self._collect_all_elements(
                                window, categorized, depth=0, context="window"
                            )

        except Exception as e:
            print(f"    ⚠️  Accessibility search error: {e}")

        total = sum(len(v) for v in categorized.values())
        print(f"    📊 Found {total} total elements:")
        for category, items in categorized.items():
            if items:
                print(f"       • {category}: {len(items)}")

        return categorized

    def get_app_window_bounds(self, app_name: Optional[str] = None) -> Optional[tuple]:
        """
        Get the bounds of the app's main window for OCR cropping.

        Returns:
            (x, y, width, height) or None
        """
        if not self.available:
            return None

        try:
            app = self._get_app(app_name)
            if not app:
                return None

            for i in range(app.childCount):
                try:
                    window = app.getChildAtIndex(i)
                    if window.getRoleName() in ["frame", "window", "dialog"]:
                        state_set = window.getState()
                        if state_set.contains(
                            self.pyatspi.STATE_ACTIVE
                        ) or state_set.contains(self.pyatspi.STATE_SHOWING):
                            component = window.queryComponent()
                            extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)
                            x, y, w, h = extents
                            return (int(x), int(y), int(w), int(h))
                except:
                    continue
        except Exception:
            pass

        return None

    def _collect_all_elements(
        self,
        container,
        categorized: Dict[str, List[Dict[str, Any]]],
        depth: int = 0,
        context: str = "window",
    ):
        """
        Recursively collect ALL UI elements with categorization.

        Args:
            container: AT-SPI element to traverse
            categorized: Dictionary to store categorized elements
            depth: Current recursion depth
            context: Context hint (menu_bar, window, etc.)
        """
        if depth > 25:
            return

        try:
            role_name = container.getRoleName().lower()

            category = self._categorize_element(role_name, context)
            element_info = self._extract_element_info(container, role_name, category)

            if element_info:
                categorized[category].append(element_info)

            new_context = context
            if role_name in ["menu bar"]:
                new_context = "menu_bar"
            elif role_name in ["menu", "menu item"]:
                new_context = "menu_items"

            for i in range(container.childCount):
                try:
                    child = container.getChildAtIndex(i)
                    self._collect_all_elements(
                        child, categorized, depth + 1, new_context
                    )
                except:
                    continue

        except:
            pass

    def _categorize_element(self, role_name: str, context: str) -> str:
        """
        Categorize an element based on its role and context.

        Returns:
            Category name: interactive, menu_bar, menu_items, static, or structural
        """
        if context == "menu_bar" or role_name in ["menu bar"]:
            return "menu_bar"

        if context == "menu_items" or role_name in ["menu", "menu item"]:
            return "menu_items"

        interactive_roles = [
            "push button",
            "button",
            "check box",
            "radio button",
            "text",
            "entry",
            "combo box",
            "slider",
            "spin button",
            "link",
            "tab",
            "toggle button",
            "password text",
        ]
        if role_name in interactive_roles:
            return "interactive"

        static_roles = [
            "label",
            "static",
            "heading",
            "paragraph",
            "image",
            "icon",
        ]
        if role_name in static_roles:
            return "static"

        structural_roles = [
            "panel",
            "filler",
            "scroll pane",
            "split pane",
            "tool bar",
            "list",
            "table",
            "tree",
            "tree table",
            "page tab list",
        ]
        if role_name in structural_roles:
            return "structural"

        return "structural"

    def _extract_element_info(
        self, container, role_name: str, category: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract relevant information from an AT-SPI element.

        Returns:
            Dictionary with element info or None if element should be skipped
        """
        try:
            identifier = getattr(container, "name", "")
            description = getattr(container, "description", "")

            if not identifier and not description:
                return None

            center = None
            bounds = None
            is_valid_for_clicking = True
            try:
                component = container.queryComponent()
                extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)
                x, y, w, h = extents

                if w <= 0 or h <= 0:
                    is_valid_for_clicking = False
                elif x < 0 or y < 0 or x > self.screen_width or y > self.screen_height:
                    is_valid_for_clicking = False

                if is_valid_for_clicking:
                    center = [int(x + w / 2), int(y + h / 2)]
                    bounds = [int(x), int(y), int(w), int(h)]

                    if y < 40 and category == "menu_bar":
                        is_valid_for_clicking = False
            except:
                pass

            if not is_valid_for_clicking:
                return None

            has_actions = False
            try:
                action_iface = container.queryAction()
                has_actions = action_iface.nActions > 0
            except:
                pass

            state_set = container.getState()
            enabled = state_set.contains(self.pyatspi.STATE_ENABLED)

            return {
                "identifier": identifier,
                "role": role_name,
                "description": description,
                "label": description or identifier,
                "title": description or identifier,
                "category": category,
                "center": center,
                "bounds": bounds,
                "has_actions": has_actions,
                "enabled": enabled,
                "_element": container,
            }

        except:
            return None

    def _collect_interactive_elements(
        self, container, elements: List[Dict[str, Any]], depth=0
    ):
        """Recursively collect interactive elements for LLM context."""
        if depth > 20:
            return

        try:
            is_interactive = False

            role_name = container.getRoleName().lower()
            state_set = container.getState()

            if state_set.contains(self.pyatspi.STATE_ENABLED):
                try:
                    action_iface = container.queryAction()
                    if action_iface.nActions > 0:
                        is_interactive = True
                except:
                    pass

            if is_interactive:
                identifier = getattr(container, "name", "")
                description = getattr(container, "description", "")

                if identifier or description:
                    try:
                        component = container.queryComponent()
                        extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)
                        x, y, w, h = extents

                        elements.append(
                            {
                                "identifier": identifier,
                                "role": role_name,
                                "description": description,
                                "label": description or identifier,
                                "title": description or identifier,
                                "center": [int(x + w / 2), int(y + h / 2)],
                                "bounds": [int(x), int(y), int(w), int(h)],
                            }
                        )
                    except Exception:
                        # If we can't get coordinates, skip this element
                        pass

            for i in range(container.childCount):
                try:
                    child = container.getChildAtIndex(i)
                    self._collect_interactive_elements(child, elements, depth + 1)
                except:
                    continue

        except:
            pass

    def find_elements(
        self,
        label: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find UI elements and return their coordinates.

        Args:
            label: Element label or text to find
            role: AT-SPI role
            app_name: Application name

        Returns:
            List of elements with coordinates and metadata
        """
        if not self.available:
            return []

        elements = []

        try:
            from ...utils.ui import console

            app = self._get_app(app_name)
            if not app:
                return []

            windows = self._get_app_windows(app)
            console.print(
                f"    [dim]Searching {len(windows)} window(s) for '{label}'[/dim]"
            )

            for window in windows:
                self._traverse_and_collect(window, label, role, elements)

            console.print(f"  [green]Found {len(elements)} elements[/green]")

        except Exception:
            pass

        return elements

    def is_app_running(self, app_name: str) -> bool:
        """
        Check if an application is currently running.

        Args:
            app_name: Application name to check

        Returns:
            True if app is running, False otherwise
        """
        if not self.available:
            return False

        try:
            app = self._get_app(app_name)
            return app is not None
        except Exception:
            return False

    def get_running_app_names(self) -> List[str]:
        """
        Get names of all currently running applications.

        Returns:
            List of running application names
        """
        if not self.available:
            return []

        try:
            app_names = []
            for app in self.desktop:
                try:
                    if hasattr(app, "name") and app.name:
                        app_names.append(app.name)
                except:
                    continue
            return app_names
        except Exception:
            return []

    def get_frontmost_app_name(self) -> Optional[str]:
        """
        Get the name of the application with an active window.

        Returns:
            Name of app with active window, or None if unavailable
        """
        if not self.available:
            return None

        try:
            for app in self.desktop:
                try:
                    for i in range(app.childCount):
                        try:
                            window = app.getChildAtIndex(i)
                            state_set = window.getState()
                            if state_set.contains(self.pyatspi.STATE_ACTIVE):
                                return app.name
                        except:
                            continue
                except:
                    continue
            return None
        except Exception:
            return None

    def is_app_frontmost(self, app_name: str) -> bool:
        """
        Check if an application has an active window.

        Args:
            app_name: Application name to check

        Returns:
            True if app has active window, False otherwise
        """
        if not self.available:
            return False

        frontmost_name = self.get_frontmost_app_name()
        if not frontmost_name:
            return False

        app_lower = app_name.lower().strip()
        front_lower = frontmost_name.lower().strip()

        if app_lower in front_lower or front_lower in app_lower:
            return True
        return False

    def get_text_from_app(self, app_name: str, role: Optional[str] = None) -> List[str]:
        """
        Extract all text values from an application using AT-SPI API.
        Useful for reading Calculator results, text editor content, etc.

        Args:
            app_name: Application name
            role: Optional role filter (e.g., "StaticText", "TextField")

        Returns:
            List of text strings found in the application
        """
        if not self.available:
            return []

        texts = []

        try:
            app = self._get_app(app_name)
            if not app:
                return []

            windows = self._get_app_windows(app)
            for window in windows:
                self._collect_text_values(window, texts, role)

        except Exception as e:
            print_warning(f"Failed to extract text: {e}")

        return texts

    def _collect_text_values(
        self,
        container,
        texts: List[str],
        role_filter: Optional[str] = None,
        depth: int = 0,
    ):
        """Recursively collect text values from accessibility tree."""
        if depth > 20:
            return

        try:
            role_name = container.getRoleName().lower()

            if role_filter and role_name != role_filter.lower():
                pass
            else:
                if hasattr(container, "name") and container.name:
                    value = str(container.name).strip()
                    if value and value not in texts:
                        texts.append(value)

                if hasattr(container, "description") and container.description:
                    desc = str(container.description).strip()
                    if desc and desc not in texts:
                        texts.append(desc)

            for i in range(container.childCount):
                try:
                    child = container.getChildAtIndex(i)
                    self._collect_text_values(child, texts, role_filter, depth + 1)
                except:
                    continue

        except:
            pass

    def _perform_click(self, element):
        """Perform click action on element using AT-SPI."""
        try:
            action_iface = element.queryAction()
            for i in range(action_iface.nActions):
                action_name = action_iface.getName(i)
                if "click" in action_name.lower() or "press" in action_name.lower():
                    action_iface.doAction(i)
                    return True
            raise Exception("Element does not support click/press action")
        except Exception as e:
            raise Exception(f"Click action failed: {str(e)}")

    def _get_app(self, app_name: Optional[str] = None):
        """
        Get application reference by name.
        Uses cached reference when available.

        IMPORTANT: This should ONLY be called after open_application has set the active app.
        No frontmost app fallbacks - if the app isn't cached or found, we fail.
        """
        print(f"        [_get_app] Looking for app: '{app_name}'")

        if not app_name:
            raise ValueError("app_name is required - no frontmost app fallback")

        if self.current_app_name and self.current_app_ref:
            if app_name.lower() == self.current_app_name.lower():
                print(f"        [_get_app] 🚀 Using CACHED reference for '{app_name}'")
                return self.current_app_ref

        try:
            for app in self.desktop:
                try:
                    if hasattr(app, "name") and app.name:
                        if (
                            app_name.lower() in app.name.lower()
                            or app.name.lower() in app_name.lower()
                        ):
                            app_title = app.name
                            print(f"        [_get_app] getAppRef returned: {app_title}")

                            if app_title and (
                                app_name.lower() in app_title.lower()
                                or app_title.lower() in app_name.lower()
                            ):
                                print(
                                    f"        [_get_app] ✅ App name matches, returning {app_title}"
                                )
                                return app
                            else:
                                print(
                                    f"        [_get_app] ❌ WRONG APP! Requested '{app_name}' but got '{app_title}'"
                                )
                                raise ValueError(
                                    f"App name mismatch: requested '{app_name}', got '{app_title}'"
                                )
                except Exception:
                    continue

            raise Exception(
                f"App '{app_name}' not found. Make sure it's opened with open_application first."
            )
        except Exception as e:
            print(f"        [_get_app] ❌ Failed to get app: {e}")
            raise

    def _get_app_windows(self, app):
        """
        Get all windows for an application.
        Simple and fast - retries are handled at the app reference level.
        """
        if not app:
            print("      [_get_app_windows] app is None, returning []")
            return []

        app_name_attr = getattr(app, "name", "Unknown")
        print(f"      [_get_app_windows] Checking '{app_name_attr}'...")

        windows = []
        try:
            for i in range(app.childCount):
                try:
                    child = app.getChildAtIndex(i)
                    role_name = child.getRoleName().lower()
                    if role_name in ["frame", "window", "dialog"]:
                        windows.append(child)
                except:
                    continue
        except:
            pass

        print(f"      [_get_app_windows] ✅ Returning {len(windows)} windows")
        return windows

    def _find_element(self, app, target_text, depth=0):
        """Recursively find element by text."""
        if depth > 20:
            return None

        try:
            windows = self._get_app_windows(app)

            for window in windows:
                result = self._search_tree_for_element(window, target_text, depth)
                if result:
                    return result

        except:
            pass

        return None

    def _search_tree_for_element(self, container, target_text, depth=0):
        """Recursively search accessibility tree for element with target text."""
        if depth > 20:
            return None

        try:
            if self._element_matches_text(container, target_text):
                return container

            for i in range(container.childCount):
                try:
                    child = container.getChildAtIndex(i)
                    result = self._search_tree_for_element(
                        child, target_text, depth + 1
                    )
                    if result:
                        return result
                except:
                    continue

        except:
            pass

        return None

    def _element_matches_text(self, element, target_text):
        """Check if element's text attributes match the target text. EXACT MATCH ONLY."""
        try:
            elem_name = getattr(element, "name", "").lower()
            if elem_name == target_text:
                return True

            elem_desc = getattr(element, "description", "").lower()
            if elem_desc == target_text:
                return True

        except:
            pass

        return False

    def _traverse_and_collect(self, container, label, role, elements, depth=0):
        """Traverse AT-SPI tree and collect matching elements with coordinates."""
        if depth > 20:
            return

        try:
            matches = False
            matched_text = None

            if label:
                elem_name = getattr(container, "name", "")
                elem_desc = getattr(container, "description", "")

                if label.lower() in elem_name.lower():
                    matches = True
                    matched_text = elem_name
                elif label.lower() in elem_desc.lower():
                    matches = True
                    matched_text = elem_desc

            if matches and role:
                elem_role = container.getRoleName().lower()
                if role.lower() not in elem_role:
                    matches = False

            if matches:
                try:
                    component = container.queryComponent()
                    extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)
                    x, y, w, h = extents

                    elements.append(
                        {
                            "center": (int(x + w / 2), int(y + h / 2)),
                            "bounds": (int(x), int(y), int(w), int(h)),
                            "role": container.getRoleName(),
                            "title": matched_text,
                            "detection_method": "atspi",
                            "confidence": 1.0,
                        }
                    )
                except:
                    pass

            for i in range(container.childCount):
                try:
                    child = container.getChildAtIndex(i)
                    self._traverse_and_collect(child, label, role, elements, depth + 1)
                except:
                    continue

        except:
            pass
