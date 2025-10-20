"""
macOS Accessibility API using atomacos for 100% accurate element interaction.
"""

from typing import List, Optional, Dict, Any
import platform


class MacOSAccessibility:
    """
    macOS accessibility using atomacos library.
    Provides 100% accurate element coordinates and direct interaction via AX APIs.
    """

    def __init__(self):
        """Initialize macOS accessibility with atomacos."""
        self.available = self._check_availability()
        if self.available:
            self._initialize_api()

    def _check_availability(self) -> bool:
        """Check if atomacos is available and platform is macOS."""
        if platform.system().lower() != "darwin":
            return False

        try:
            import atomacos

            return True
        except ImportError:
            return False

    def _initialize_api(self):
        """Initialize atomacos and check accessibility permissions."""
        try:
            import atomacos

            self.atomacos = atomacos

            try:
                app = atomacos.getAppRefByBundleId("com.apple.finder")
                print("  ✅ Accessibility API ready with 100% accurate coordinates!")
            except Exception:
                print("  ⚠️  Accessibility permissions not granted")
                print(
                    "  ℹ️  Enable in: System Settings → Privacy & Security → Accessibility"
                )
                self.available = False

        except Exception as e:
            print(f"  ⚠️  Failed to initialize Accessibility: {e}")
            self.available = False

    def click_element(self, label: str, app_name: Optional[str] = None) -> bool:
        """
        Find and click element directly using accessibility API.
        This is the primary method for interaction.

        Args:
            label: Text to search for in element (matches AXIdentifier, AXAttributedDescription, etc.)
            app_name: Application name to search in

        Returns:
            True if clicked successfully
        """
        if not self.available:
            return False

        try:
            app = self._get_app(app_name)
            element = self._find_element(app, label)

            if element:
                identifier = getattr(element, "AXIdentifier", "N/A")
                self._perform_click(element)
                print(f"    ✅ Clicked '{identifier}' via Accessibility API")
                return True

            return False

        except Exception as e:
            print(f"    ⚠️  Accessibility click failed: {e}")
            return False

    def get_all_interactive_elements(
        self, app_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all interactive elements (buttons, text fields, etc.) with their identifiers.
        This allows the LLM to see what's available and choose the right identifier.

        Args:
            app_name: Application name to search in

        Returns:
            List of elements with their AXIdentifier, AXRole, and description
        """
        if not self.available:
            return []

        elements = []

        try:
            app = self._get_app(app_name)
            windows = self._get_app_windows(app)

            for window in windows:
                self._collect_interactive_elements(window, elements)

        except Exception as e:
            print(f"    ⚠️  Failed to collect elements: {e}")

        return elements

    def _collect_interactive_elements(
        self, container, elements: List[Dict[str, Any]], depth=0
    ):
        """
        Recursively collect all interactive elements (buttons, text fields, etc.)
        with their identifiers for LLM context.
        """
        if depth > 20:
            return

        try:
            elem_role = getattr(container, "AXRole", "")

            if str(elem_role) == "AXApplication":
                if hasattr(container, "AXChildren") and container.AXChildren:
                    for child in container.AXChildren:
                        self._collect_interactive_elements(child, elements, depth + 1)
                return

            interactive_roles = [
                "AXButton",
                "AXTextField",
                "AXTextArea",
                "AXCheckBox",
                "AXRadioButton",
                "AXPopUpButton",
                "AXMenuButton",
                "AXSlider",
            ]

            if any(role in str(elem_role) for role in interactive_roles):
                identifier = getattr(container, "AXIdentifier", "")
                description = ""

                if hasattr(container, "AXAttributedDescription"):
                    try:
                        desc_obj = container.AXAttributedDescription
                        description = str(desc_obj).split("{")[0].strip()
                    except:
                        pass

                if not description:
                    description = getattr(container, "AXTitle", "") or getattr(
                        container, "AXValue", ""
                    )

                if identifier or description:
                    elements.append(
                        {
                            "identifier": identifier,
                            "role": str(elem_role).replace("AX", ""),
                            "description": description,
                        }
                    )

            if hasattr(container, "AXChildren") and container.AXChildren:
                for child in container.AXChildren:
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
        Fallback method when direct clicking fails.

        Args:
            label: Element label or text to find
            role: Accessibility role (Button, StaticText, etc.)
            app_name: Application name

        Returns:
            List of elements with coordinates and metadata
        """
        if not self.available:
            return []

        elements = []

        try:
            app = self._get_app(app_name)
            windows = self._get_app_windows(app)

            print(f"    🪟 Searching {len(windows)} window(s) for '{label}'")

            for window in windows:
                self._traverse_and_collect(window, label, role, elements)

            print(f"  ✅ Found {len(elements)} elements")

        except Exception as e:
            print(f"    Traversal error: {e}")

        return elements

    def _get_app(self, app_name: Optional[str] = None):
        """Get application reference by name or frontmost app."""
        if app_name:
            return self.atomacos.getAppRefByLocalizedName(app_name)
        else:
            return self.atomacos.NativeUIElement.getFrontmostApp()

    def _get_app_windows(self, app):
        """Get all windows for an application."""
        if hasattr(app, "AXWindows") and app.AXWindows:
            return app.AXWindows
        elif hasattr(app, "AXChildren") and app.AXChildren:
            return [
                child
                for child in app.AXChildren
                if hasattr(child, "AXRole")
                and str(child.AXRole) in ["AXWindow", "AXSheet", "AXDrawer"]
            ]
        return []

    def _find_element(self, app, label: str, depth=0):
        """
        Recursively find element by label.
        Returns the actual atomacos element object for direct interaction.
        """
        if depth > 20:
            return None

        windows = self._get_app_windows(app)
        if not windows:
            return None

        for window in windows:
            result = self._search_tree_for_element(window, label.lower(), depth)
            if result:
                return result

        return None

    def _search_tree_for_element(self, container, target_text, depth=0):
        """
        Recursively search accessibility tree for element with target text.
        Searches AXIdentifier, AXAttributedDescription, AXTitle, AXValue, etc.
        """
        if depth > 20:
            return None

        try:
            elem_role = getattr(container, "AXRole", "")

            if str(elem_role) == "AXApplication":
                if hasattr(container, "AXChildren") and container.AXChildren:
                    for child in container.AXChildren:
                        result = self._search_tree_for_element(
                            child, target_text, depth + 1
                        )
                        if result:
                            return result
                return None

            if self._element_matches_text(container, target_text):
                return container

            if hasattr(container, "AXChildren") and container.AXChildren:
                for child in container.AXChildren:
                    result = self._search_tree_for_element(
                        child, target_text, depth + 1
                    )
                    if result:
                        return result

        except:
            pass

        return None

    def _element_matches_text(self, element, target_text):
        """
        Check if element's text attributes match the target text.
        Checks AXIdentifier, AXAttributedDescription, AXTitle, AXValue, AXDescription.
        """
        try:
            if hasattr(element, "AXIdentifier") and element.AXIdentifier:
                identifier = str(element.AXIdentifier).lower()
                if target_text in identifier or identifier in target_text:
                    return True

            if (
                hasattr(element, "AXAttributedDescription")
                and element.AXAttributedDescription
            ):
                try:
                    desc_str = str(element.AXAttributedDescription).lower()
                    if target_text in desc_str or desc_str.startswith(target_text):
                        return True
                except:
                    pass

            if hasattr(element, "AXTitle") and element.AXTitle:
                if target_text in str(element.AXTitle).lower():
                    return True

            if hasattr(element, "AXValue") and element.AXValue:
                if target_text in str(element.AXValue).lower():
                    return True

            if hasattr(element, "AXDescription") and element.AXDescription:
                if target_text in str(element.AXDescription).lower():
                    return True

        except:
            pass

        return False

    def _perform_click(self, element):
        """Perform click action on element using atomacos."""
        try:
            if hasattr(element, "Press"):
                element.Press()
            elif hasattr(element, "AXPress"):
                element.AXPress()
            else:
                raise Exception("Element does not support click action")
        except Exception as e:
            raise Exception(f"Click action failed: {e}")

    def _traverse_and_collect(self, container, label, role, elements, depth=0):
        """Traverse accessibility tree and collect matching elements with coordinates."""
        if depth > 20:
            return

        try:
            elem_role = getattr(container, "AXRole", "")

            if str(elem_role) == "AXApplication":
                if hasattr(container, "AXChildren") and container.AXChildren:
                    for child in container.AXChildren:
                        self._traverse_and_collect(
                            child, label, role, elements, depth + 1
                        )
                return

            matches = False
            matched_text = None

            if label:
                if hasattr(container, "AXTitle") and container.AXTitle:
                    if label.lower() in str(container.AXTitle).lower():
                        matches = True
                        matched_text = str(container.AXTitle)

                if not matches and hasattr(container, "AXValue") and container.AXValue:
                    if label.lower() in str(container.AXValue).lower():
                        matches = True
                        matched_text = str(container.AXValue)

                if (
                    not matches
                    and hasattr(container, "AXDescription")
                    and container.AXDescription
                ):
                    if label.lower() in str(container.AXDescription).lower():
                        matches = True
                        matched_text = str(container.AXDescription)

            if matches and role:
                if role.lower() not in str(elem_role).lower():
                    matches = False

            if matches:
                try:
                    position = container.AXPosition
                    size = container.AXSize
                    x, y = position
                    w, h = size

                    elements.append(
                        {
                            "center": (int(x + w / 2), int(y + h / 2)),
                            "bounds": (int(x), int(y), int(w), int(h)),
                            "role": elem_role,
                            "title": matched_text,
                            "detection_method": "accessibility",
                            "confidence": 1.0,
                        }
                    )
                except:
                    pass

            if hasattr(container, "AXChildren") and container.AXChildren:
                for child in container.AXChildren:
                    self._traverse_and_collect(child, label, role, elements, depth + 1)

        except:
            pass
