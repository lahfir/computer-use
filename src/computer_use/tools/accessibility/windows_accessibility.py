"""
Windows UI Automation API using pywinauto for 100% accurate element interaction.
"""

from typing import List, Optional, Dict, Any
import platform

from ...utils.ui import print_success, print_warning, print_info, console
from ...config.timing_config import get_timing_config


class WindowsAccessibility:
    """
    Windows UI Automation using pywinauto library.
    Provides 100% accurate element coordinates and direct interaction via UIA APIs.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        """Initialize Windows UI Automation with pywinauto."""
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
            desktop = self.Desktop(backend="uia")
            windows = [
                w
                for w in desktop.windows()
                if app_name.lower() in w.window_text().lower()
            ]
            if windows:
                app_title = windows[0].window_text()
                if app_title and (
                    app_name.lower() in app_title.lower()
                    or app_title.lower() in app_name.lower()
                ):
                    print(
                        f"        [set_active_app] ✅ Cached '{app_title}' as active app"
                    )
                    self.current_app_name = app_name
                    self.current_app_ref = windows[0]
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
        """Check if pywinauto is available and platform is Windows."""
        if platform.system().lower() != "windows":
            return False

        try:
            import pywinauto  # noqa: F401

            return True
        except ImportError:
            return False

    def _initialize_api(self):
        """Initialize pywinauto and check UI Automation permissions."""
        try:
            import pywinauto
            from pywinauto import Desktop

            self.pywinauto = pywinauto
            self.Desktop = Desktop

            try:
                desktop = Desktop(backend="uia")
                desktop.windows()
                print_success("Accessibility API ready with 100% accurate coordinates")
            except Exception:
                print_warning("UI Automation permissions issue")
                print_info("May need to run with administrator privileges")
                self.available = False

        except Exception as e:
            print_warning(f"Failed to initialize UI Automation: {e}")
            self.available = False

    def click_element(self, label: str, app_name: Optional[str] = None) -> tuple:
        """
        Find and click element directly using UI Automation API.

        Args:
            label: Text to search for in element
            app_name: Application name to search in

        Returns:
            Tuple of (success: bool, element: Optional[element])
        """
        if not self.available:
            return (False, None)

        try:
            desktop = self.Desktop(backend="uia")

            if app_name:
                windows = [
                    w
                    for w in desktop.windows()
                    if app_name.lower() in w.window_text().lower()
                ]
            else:
                windows = [desktop.windows()[0]] if desktop.windows() else []

            if not windows:
                return (False, None)

            window = windows[0]
            element = self._find_element(window, label.lower())

            if element:
                from ...utils.ui import console, print_success, print_warning

                elem_text = element.window_text()
                console.print(f"    [dim]Found: {elem_text}[/dim]")

                try:
                    element.click_input()
                    print_success(f"Clicked '{elem_text}' via UI Automation")
                    return (True, element)
                except Exception as e:
                    print_warning(f"Native click failed: {e}")
                    return (False, element)

            return (False, None)

        except Exception as e:
            from ...utils.ui import print_warning

            print_warning(f"UI Automation search failed: {e}")
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
                    parent = current.parent()
                    if parent:
                        parent_type = (
                            parent.element_info.control_type
                            if hasattr(parent, "element_info")
                            else "Unknown"
                        )
                        console.print(
                            f"    [dim]Trying parent {depth} ({parent_type})...[/dim]"
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
            desktop = self.Desktop(backend="uia")

            if app_name:
                windows = [
                    w
                    for w in desktop.windows()
                    if app_name.lower() in w.window_text().lower()
                ]
            else:
                windows = [desktop.windows()[0]] if desktop.windows() else []

            if not windows:
                return []

            window = windows[0]
            self._collect_interactive_elements(window, elements)

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
            desktop = self.Desktop(backend="uia")

            for attempt in range(timing.accessibility_retry_count):
                print(
                    f"    🔄 Attempt {attempt + 1}/{timing.accessibility_retry_count}: Getting fresh app reference..."
                )

                if attempt > 0:
                    print("        [RETRY] Clearing app cache to force fresh lookup...")
                    self.current_app_name = None
                    self.current_app_ref = None

                if app_name:
                    windows = [
                        w
                        for w in desktop.windows()
                        if app_name.lower() in w.window_text().lower()
                    ]
                else:
                    windows = [desktop.windows()[0]] if desktop.windows() else []

                if windows:
                    app = windows[0]
                    app_title = app.window_text()
                    print(f"    ✓ Got app reference: {app_title}")
                    print(f"    📊 Found {len(windows)} window(s)")

                    if windows:
                        print(
                            f"    ✅ SUCCESS on attempt {attempt + 1}: {len(windows)} window(s)"
                        )
                        break
                else:
                    print(f"    ⚠️  Attempt {attempt + 1}/3: 0 windows!")

            if not windows:
                print("    ❌ FAILED: No windows found after 3 retries!")

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
                    frontmost_windows = [
                        w
                        for w in desktop.windows()
                        if frontmost.lower() in w.window_text().lower()
                    ]
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
            desktop = self.Desktop(backend="uia")
            windows = [
                w
                for w in desktop.windows()
                if app_name.lower() in w.window_text().lower()
            ]
            return len(windows) > 0
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
            desktop = self.Desktop(backend="uia")
            windows = desktop.windows()
            app_names = []
            seen = set()
            for window in windows:
                name = window.window_text()
                if name and name not in seen:
                    app_names.append(name)
                    seen.add(name)
            return app_names
        except Exception:
            return []

    def get_frontmost_app_name(self) -> Optional[str]:
        """
        Get the name of the frontmost (active) application window.

        Returns:
            Name of frontmost app, or None if unavailable
        """
        if not self.available:
            return None

        try:
            desktop = self.Desktop(backend="uia")
            windows = desktop.windows()
            for window in windows:
                if window.has_focus():
                    return window.window_text()
            return None
        except Exception:
            return None

    def is_app_frontmost(self, app_name: str) -> bool:
        """
        Check if an application window is currently the foreground (active) window.

        Args:
            app_name: Application name to check

        Returns:
            True if app is in foreground, False otherwise
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
        Extract all text values from an application using UI Automation API.
        Useful for reading Calculator results, text editor content, etc.

        Args:
            app_name: Application name
            role: Optional role filter (e.g., "Text", "Edit")

        Returns:
            List of text strings found in the application
        """
        if not self.available:
            return []

        texts = []

        try:
            desktop = self.Desktop(backend="uia")
            windows = [
                w
                for w in desktop.windows()
                if app_name.lower() in w.window_text().lower()
            ]

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
            ctrl_type = container.element_info.control_type

            if role_filter and ctrl_type.lower() != role_filter.lower():
                pass
            else:
                window_text = container.window_text()
                if window_text and window_text.strip() and window_text not in texts:
                    texts.append(window_text.strip())

                elem_name = getattr(container.element_info, "name", "")
                if elem_name and elem_name.strip() and elem_name not in texts:
                    texts.append(elem_name.strip())

            for child in container.children():
                self._collect_text_values(child, texts, role_filter, depth + 1)

        except:
            pass

    def _perform_click(self, element):
        """Perform click action on element using UI Automation."""
        try:
            element.click_input()
            return True
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
            desktop = self.Desktop(backend="uia")
            windows = [
                w
                for w in desktop.windows()
                if app_name.lower() in w.window_text().lower()
            ]

            if windows:
                app_title = windows[0].window_text()
                print(f"        [_get_app] getAppRef returned: {app_title}")

                if app_title and (
                    app_name.lower() in app_title.lower()
                    or app_title.lower() in app_name.lower()
                ):
                    print(
                        f"        [_get_app] ✅ App name matches, returning {app_title}"
                    )
                    return windows[0]
                else:
                    print(
                        f"        [_get_app] ❌ WRONG APP! Requested '{app_name}' but got '{app_title}'"
                    )
                    raise ValueError(
                        f"App name mismatch: requested '{app_name}', got '{app_title}'"
                    )

            raise Exception(
                f"App '{app_name}' not found. Make sure it's opened with open_application first."
            )
        except Exception as e:
            print(f"        [_get_app] ❌ Failed to get app: {e}")
            raise

    def get_app_window_bounds(self, app_name: Optional[str] = None) -> Optional[tuple]:
        """
        Get the bounds of the app's main window for OCR cropping.

        Returns:
            (x, y, width, height) or None
        """
        if not self.available:
            return None

        try:
            desktop = self.Desktop(backend="uia")

            if app_name:
                windows = [
                    w
                    for w in desktop.windows()
                    if app_name.lower() in w.window_text().lower()
                ]
            else:
                windows = [desktop.windows()[0]] if desktop.windows() else []

            if windows:
                window = windows[0]
                rect = window.rectangle()
                return (rect.left, rect.top, rect.width(), rect.height())
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
            container: UI Automation element to traverse
            categorized: Dictionary to store categorized elements
            depth: Current recursion depth
            context: Context hint (menu_bar, window, etc.)
        """
        if depth > 25:
            return

        try:
            ctrl_type = container.element_info.control_type

            category = self._categorize_element(ctrl_type, context)
            element_info = self._extract_element_info(container, ctrl_type, category)

            if element_info:
                categorized[category].append(element_info)

            new_context = context
            if ctrl_type in ["MenuBar"]:
                new_context = "menu_bar"
            elif ctrl_type in ["Menu", "MenuItem"]:
                new_context = "menu_items"

            for child in container.children():
                self._collect_all_elements(child, categorized, depth + 1, new_context)

        except:
            pass

    def _categorize_element(self, ctrl_type: str, context: str) -> str:
        """
        Categorize an element based on its control type and context.

        Returns:
            Category name: interactive, menu_bar, menu_items, static, or structural
        """
        if context == "menu_bar" or ctrl_type in ["MenuBar"]:
            return "menu_bar"

        if context == "menu_items" or ctrl_type in ["Menu", "MenuItem"]:
            return "menu_items"

        interactive_types = [
            "Button",
            "Edit",
            "ComboBox",
            "ListItem",
            "CheckBox",
            "RadioButton",
            "TabItem",
            "Hyperlink",
            "Slider",
            "Spinner",
        ]
        if ctrl_type in interactive_types:
            return "interactive"

        static_types = [
            "Text",
            "Image",
            "StatusBar",
        ]
        if ctrl_type in static_types:
            return "static"

        structural_types = [
            "Pane",
            "Group",
            "ToolBar",
            "List",
            "Table",
            "Tree",
            "TabControl",
            "ScrollBar",
            "SplitButton",
        ]
        if ctrl_type in structural_types:
            return "structural"

        return "structural"

    def _extract_element_info(
        self, container, ctrl_type: str, category: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract relevant information from a UI Automation element.

        Returns:
            Dictionary with element info or None if element should be skipped
        """
        try:
            identifier = container.window_text()
            description = getattr(container.element_info, "name", "")

            if not identifier and not description:
                return None

            center = None
            bounds = None
            is_valid_for_clicking = True
            try:
                rect = container.rectangle()
                x, y = rect.left, rect.top
                w, h = rect.width(), rect.height()

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

            enabled = False
            try:
                enabled = container.is_enabled()
            except:
                pass

            return {
                "identifier": identifier,
                "role": ctrl_type,
                "description": description,
                "label": description or identifier,
                "title": description or identifier,
                "category": category,
                "center": center,
                "bounds": bounds,
                "has_actions": True,
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

            ctrl_type = container.element_info.control_type
            is_enabled = container.is_enabled()

            if is_enabled and ctrl_type in [
                "Button",
                "Edit",
                "ComboBox",
                "ListItem",
                "MenuItem",
                "CheckBox",
                "RadioButton",
                "TabItem",
            ]:
                is_interactive = True

            if is_interactive:
                identifier = container.window_text()
                description = getattr(container.element_info, "name", "")

                if identifier or description:
                    try:
                        rect = container.rectangle()
                        x, y = rect.left, rect.top
                        w, h = rect.width(), rect.height()

                        elements.append(
                            {
                                "identifier": identifier,
                                "role": ctrl_type,
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

            for child in container.children():
                self._collect_interactive_elements(child, elements, depth + 1)

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
            role: UI Automation control type
            app_name: Application name

        Returns:
            List of elements with coordinates and metadata
        """
        if not self.available:
            return []

        elements = []

        try:
            from ...utils.ui import console

            desktop = self.Desktop(backend="uia")

            if app_name:
                windows = [
                    w
                    for w in desktop.windows()
                    if app_name.lower() in w.window_text().lower()
                ]
            else:
                windows = [desktop.windows()[0]] if desktop.windows() else []

            console.print(
                f"    [dim]Searching {len(windows)} window(s) for '{label}'[/dim]"
            )

            for window in windows:
                self._traverse_and_collect(window, label, role, elements)

            console.print(f"  [green]Found {len(elements)} elements[/green]")

        except Exception:
            pass

        return elements

    def _get_app_windows(self, app):
        """
        Get all windows for an application.
        Simple and fast - retries are handled at the app reference level.
        """
        if not app:
            print("      [_get_app_windows] app is None, returning []")
            return []

        app_title = app.window_text() if hasattr(app, "window_text") else "Unknown"
        print(f"      [_get_app_windows] Checking '{app_title}'...")

        try:
            windows = [app] if app else []
            print(f"      [_get_app_windows] ✅ Returning {len(windows)} windows")
            return windows
        except:
            print("      [_get_app_windows] ❌ Returning [] - no windows found")
            return []

    def _find_element(self, container, target_text, depth=0):
        """Recursively find element by text."""
        if depth > 20:
            return None

        try:
            if self._element_matches_text(container, target_text):
                return container

            for child in container.children():
                result = self._find_element(child, target_text, depth + 1)
                if result:
                    return result

        except:
            pass

        return None

    def _element_matches_text(self, element, target_text):
        """Check if element's text attributes match the target text. EXACT MATCH ONLY."""
        try:
            window_text = element.window_text().lower()
            if window_text == target_text:
                return True

            elem_name = getattr(element.element_info, "name", "").lower()
            if elem_name == target_text:
                return True

        except:
            pass

        return False

    def _traverse_and_collect(self, container, label, role, elements, depth=0):
        """Traverse UI tree and collect matching elements with coordinates."""
        if depth > 20:
            return

        try:
            matches = False
            matched_text = None

            if label:
                window_text = container.window_text()
                if label.lower() in window_text.lower():
                    matches = True
                    matched_text = window_text

            if matches and role:
                ctrl_type = container.element_info.control_type
                if role.lower() not in ctrl_type.lower():
                    matches = False

            if matches:
                try:
                    rect = container.rectangle()
                    center_x = (rect.left + rect.right) // 2
                    center_y = (rect.top + rect.bottom) // 2

                    elements.append(
                        {
                            "center": (center_x, center_y),
                            "bounds": (
                                rect.left,
                                rect.top,
                                rect.width(),
                                rect.height(),
                            ),
                            "role": container.element_info.control_type,
                            "title": matched_text,
                            "detection_method": "windows_uia",
                            "confidence": 1.0,
                        }
                    )
                except:
                    pass

            for child in container.children():
                self._traverse_and_collect(child, label, role, elements, depth + 1)

        except:
            pass
