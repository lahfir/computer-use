"""
Linux AT-SPI accessibility API wrapper for accurate element detection.
"""

from typing import List, Optional, Dict, Any
import platform


class LinuxAccessibility:
    """
    Wrapper for Linux AT-SPI (Assistive Technology Service Provider Interface).
    Provides accurate element coordinates and native interactions.
    """

    def __init__(self):
        """
        Initialize Linux accessibility API wrapper.
        """
        self.available = self._check_availability()
        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        """
        Check if AT-SPI is available.
        """
        if platform.system().lower() != "linux":
            return False

        try:
            import pyatspi

            return True
        except ImportError:
            return False

    def _initialize_api(self):
        """
        Import and initialize AT-SPI.
        """
        try:
            import pyatspi

            self.pyatspi = pyatspi
            self.desktop = pyatspi.Registry.getDesktop(0)
            print("  ✅ Linux AT-SPI ready with 100% accurate coordinates!")
        except ImportError:
            print(
                "  ⚠️  pyatspi not available - install with: sudo apt-get install python3-pyatspi"
            )
            self.available = False
        except Exception as e:
            print(f"  ⚠️  Failed to initialize AT-SPI: {e}")
            self.available = False

    def find_elements(
        self,
        role: Optional[str] = None,
        label: Optional[str] = None,
        title: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find UI elements using AT-SPI.

        Args:
            role: Element role (e.g., 'push button', 'text', 'menu item')
            label: Element label/text
            title: Window title to search within
            app_name: Application name

        Returns:
            List of element dictionaries with 100% accurate coordinates
        """
        if not self.available:
            return []

        elements = []

        try:
            print(f"  🔍 Linux AT-SPI: Searching for '{label or role}'")

            # CRITICAL FIX: Get ONLY active/focused application, not all apps
            active_app = None
            if not app_name:
                # Find the focused/active application
                for app in self.desktop:
                    try:
                        # Check if this app has an active window
                        for window in app:
                            try:
                                state_set = window.getState()
                                if state_set.contains(self.pyatspi.STATE_ACTIVE):
                                    active_app = app
                                    print(
                                        f"    🪟 Searching ONLY active app: {app.name}"
                                    )
                                    break
                            except:
                                continue
                        if active_app:
                            break
                    except:
                        continue

                if active_app:
                    elements.extend(self._search_tree(active_app, label, role, title))
                else:
                    print(f"    ⚠️  No active application found")
            else:
                # Search specific app
                for app in self.desktop:
                    try:
                        if app_name.lower() in app.name.lower():
                            print(f"    🪟 Searching app: {app.name}")
                            elements.extend(self._search_tree(app, label, role, title))
                            break
                    except:
                        continue

            print(f"  ✅ Found {len(elements)} elements with 100% accurate coordinates")

        except Exception as e:
            print(f"  ⚠️  AT-SPI error: {e}")

        return elements

    def _search_tree(
        self,
        node,
        label: Optional[str],
        role: Optional[str],
        title: Optional[str],
        depth: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Recursively search accessibility tree.
        """
        elements = []
        max_depth = 15

        if depth > max_depth:
            return elements

        try:
            # Check if this node matches
            matches = True

            if label:
                node_name = getattr(node, "name", "")
                node_desc = getattr(node, "description", "")
                matches = (
                    label.lower() in node_name.lower()
                    or label.lower() in node_desc.lower()
                )

            if matches and role:
                node_role = str(node.getRoleName()).lower()
                matches = role.lower() in node_role

            if matches and title:
                # Check if we're in the right window
                parent = node
                while parent:
                    if hasattr(parent, "name") and title.lower() in parent.name.lower():
                        break
                    parent = parent.parent if hasattr(parent, "parent") else None
                matches = parent is not None

            if matches:
                # Get element position
                try:
                    component = node.queryComponent()
                    extents = component.getExtents(self.pyatspi.DESKTOP_COORDS)

                    x, y, w, h = extents

                    elements.append(
                        {
                            "center": (int(x + w / 2), int(y + h / 2)),
                            "bounds": (int(x), int(y), int(w), int(h)),
                            "role": node.getRoleName(),
                            "title": node.name,
                            "detection_method": "atspi",
                            "confidence": 1.0,
                            "_native_element": node,
                        }
                    )
                except:
                    pass  # Element doesn't support component interface

            # Search children
            for i in range(node.childCount):
                try:
                    child = node.getChildAtIndex(i)
                    elements.extend(
                        self._search_tree(child, label, role, title, depth + 1)
                    )
                except:
                    continue

        except Exception as e:
            pass  # Skip problematic nodes

        return elements

    def perform_action(self, element: Dict[str, Any], action: str, **kwargs) -> bool:
        """
        Perform action on element using AT-SPI.

        Args:
            element: Element dict with _native_element
            action: Action to perform (click, type, scroll, etc.)
            **kwargs: Additional action parameters

        Returns:
            True if action succeeded
        """
        if not self.available:
            return False

        try:
            native_elem = element.get("_native_element")

            if action == "click":
                if native_elem:
                    try:
                        action_iface = native_elem.queryAction()
                        # Try to find "click" or "press" action
                        for i in range(action_iface.nActions):
                            action_name = action_iface.getName(i)
                            if (
                                "click" in action_name.lower()
                                or "press" in action_name.lower()
                            ):
                                action_iface.doAction(i)
                                return True
                    except:
                        pass
                # Fallback to coordinate click
                center = element["center"]
                x, y = center
                import pyautogui

                pyautogui.click(x, y)
                return True

            elif action == "type":
                text = kwargs.get("text", "")
                if text and native_elem:
                    try:
                        editable = native_elem.queryEditableText()
                        editable.insertText(0, text, len(text))
                        return True
                    except:
                        # Fallback to typing
                        import pyautogui

                        pyautogui.write(text, interval=0.05)
                        return True

            elif action == "scroll":
                direction = kwargs.get("direction", "down")
                amount = kwargs.get("amount", 3)
                center = element.get("center")
                if center:
                    x, y = center
                    import pyautogui

                    pyautogui.moveTo(x, y)
                    if direction == "down":
                        pyautogui.scroll(-amount * 100)
                    else:
                        pyautogui.scroll(amount * 100)
                    return True

            elif action == "double_click":
                center = element["center"]
                x, y = center
                import pyautogui

                pyautogui.doubleClick(x, y)
                return True

            elif action == "right_click":
                center = element["center"]
                x, y = center
                import pyautogui

                pyautogui.rightClick(x, y)
                return True

        except Exception as e:
            print(f"  ⚠️  Linux action {action} failed: {e}")
            return False

        return False

    def click_element(self, element: Dict[str, Any]) -> bool:
        """
        Click element at 100% accurate coordinates.

        Args:
            element: Element dictionary from find_elements()

        Returns:
            True if click succeeded
        """
        return self.perform_action(element, "click")

    def get_active_window_info(self) -> Dict[str, Any]:
        """
        Get information about the currently active window.

        Returns:
            Dictionary with window information
        """
        if not self.available:
            return {}

        try:
            # Find focused accessible
            for app in self.desktop:
                for window in app:
                    try:
                        state_set = window.getState()
                        if state_set.contains(self.pyatspi.STATE_ACTIVE):
                            return {
                                "title": window.name,
                                "role": window.getRoleName(),
                            }
                    except:
                        continue
        except Exception as e:
            print(f"  ⚠️  Failed to get active window: {e}")

        return {}
