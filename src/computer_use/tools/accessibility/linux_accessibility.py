"""
Linux AT-SPI accessibility API using pyatspi for 100% accurate element interaction.
"""

from typing import List, Optional, Dict, Any
import platform


class LinuxAccessibility:
    """
    Linux AT-SPI using pyatspi library.
    Provides 100% accurate element coordinates and direct interaction via AT-SPI APIs.
    """

    def __init__(self):
        """Initialize Linux AT-SPI with pyatspi."""
        self.available = self._check_availability()
        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        """Check if pyatspi is available and platform is Linux."""
        if platform.system().lower() != "linux":
            return False

        try:
            import pyatspi

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
                apps = list(self.desktop)
                from ...utils.ui import print_success

                print_success("Accessibility API ready with 100% accurate coordinates")
            except Exception:
                from ...utils.ui import print_warning, print_info

                print_warning("AT-SPI permissions issue")
                print_info("Ensure accessibility is enabled in system settings")
                self.available = False

        except Exception as e:
            from ...utils.ui import print_warning

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
                    elements.append(
                        {
                            "identifier": identifier,
                            "role": role_name,
                            "description": description,
                        }
                    )

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

    def _get_app(self, app_name: Optional[str] = None):
        """Get application reference by name or active app."""
        try:
            if app_name:
                for app in self.desktop:
                    try:
                        if app_name.lower() in app.name.lower():
                            return app
                    except:
                        continue
            else:
                for app in self.desktop:
                    try:
                        for i in range(app.childCount):
                            window = app.getChildAtIndex(i)
                            state_set = window.getState()
                            if state_set.contains(self.pyatspi.STATE_ACTIVE):
                                return app
                    except:
                        continue
        except:
            pass

        return None

    def _get_app_windows(self, app):
        """Get all windows for an application."""
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
