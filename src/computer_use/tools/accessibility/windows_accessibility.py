"""
Windows UI Automation API using pywinauto for 100% accurate element interaction.
"""

from typing import List, Optional, Dict, Any
import platform


class WindowsAccessibility:
    """
    Windows UI Automation using pywinauto library.
    Provides 100% accurate element coordinates and direct interaction via UIA APIs.
    """

    def __init__(self):
        """Initialize Windows UI Automation with pywinauto."""
        self.available = self._check_availability()
        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        """Check if pywinauto is available and platform is Windows."""
        if platform.system().lower() != "windows":
            return False

        try:
            import pywinauto

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
                windows = desktop.windows()
                from ...utils.ui import print_success

                print_success("Accessibility API ready with 100% accurate coordinates")
            except Exception:
                from ...utils.ui import print_warning, print_info

                print_warning("UI Automation permissions issue")
                print_info("May need to run with administrator privileges")
                self.available = False

        except Exception as e:
            from ...utils.ui import print_warning

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
                    elements.append(
                        {
                            "identifier": identifier,
                            "role": ctrl_type,
                            "description": description,
                        }
                    )

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
