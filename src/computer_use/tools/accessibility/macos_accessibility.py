"""
macOS Accessibility API using atomacos for 100% accurate element interaction.
"""

from typing import List, Optional, Dict, Any
import platform

from ...utils.ui import print_success, print_warning, print_info, console
from ...config.timing_config import get_timing_config


class MacOSAccessibility:
    """
    macOS accessibility using atomacos library.
    Provides 100% accurate element coordinates and direct interaction via AX APIs.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        """Initialize macOS accessibility with atomacos."""
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

        # Clear old cache if switching apps
        if self.current_app_name and self.current_app_name.lower() != app_name.lower():
            print(
                f"        [set_active_app] Switching from '{self.current_app_name}' to '{app_name}'"
            )
            self.current_app_name = None
            self.current_app_ref = None

        # Get fresh reference for the newly focused app
        try:
            app = self.atomacos.getAppRefByLocalizedName(app_name)
            app_title = getattr(app, "AXTitle", "")

            if app_title and (
                app_name.lower() in app_title.lower()
                or app_title.lower() in app_name.lower()
            ):
                print(f"        [set_active_app] ✅ Cached '{app_title}' as active app")
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
        """Check if atomacos is available and platform is macOS."""
        if platform.system().lower() != "darwin":
            return False

        try:
            import atomacos  # noqa: F401

            return True
        except ImportError:
            return False

    def _initialize_api(self):
        """Initialize atomacos and check accessibility permissions."""
        try:
            import atomacos

            self.atomacos = atomacos

            try:
                atomacos.getAppRefByBundleId("com.apple.finder")

                print_success("Accessibility API ready with 100% accurate coordinates")
            except Exception:
                print_warning("Accessibility permissions not granted")
                print_info(
                    "Enable in: System Settings → Privacy & Security → Accessibility"
                )
                self.available = False

        except Exception as e:
            print_warning(f"Failed to initialize Accessibility: {e}")
            self.available = False

    def click_element(self, label: str, app_name: Optional[str] = None) -> tuple:
        """
        Find and click element directly using accessibility API.

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
            element = self._find_element(app, label)

            if element:
                identifier = getattr(element, "AXIdentifier", "N/A")
                console.print(f"    [dim]Found: {identifier}[/dim]")

                try:
                    self._perform_click(element)
                    print_success(f"Clicked '{identifier}' via Accessibility")
                    return (True, element)
                except Exception as e:
                    print_warning(f"Native click failed: {e}")
                    return (False, element)

            return (False, None)

        except Exception as e:
            print_warning(f"Accessibility search failed: {e}")
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
            # Get the atomacos element reference
            element = element_dict.get("_element")
            if not element:
                return (False, "no_element_reference")

            # Try to click the element directly first
            console.print("    [dim]Trying native click on element...[/dim]")
            try:
                self._perform_click(element)
                console.print("    [green]✅ Clicked element directly![/green]")
                return (True, "element")
            except Exception as e:
                console.print(f"    [dim]Element click failed: {e}[/dim]")

            # Traverse up to parents and try clicking them
            current = element
            for depth in range(1, max_depth + 1):
                try:
                    if hasattr(current, "AXParent") and current.AXParent:
                        parent = current.AXParent
                        parent_role = str(getattr(parent, "AXRole", "Unknown"))
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
            windows = self._get_app_windows(app)

            print(f"    Searching {len(windows)} window(s) for interactive elements")

            for window in windows:
                self._collect_interactive_elements(window, elements)

            if len(elements) == 0 and len(windows) > 0:
                frontmost = self.atomacos.NativeUIElement.getFrontmostApp()
                if frontmost and hasattr(frontmost, "AXTitle"):
                    frontmost_name = str(frontmost.AXTitle)
                    if frontmost_name.lower() != (app_name or "").lower():
                        print(
                            f"    ⚠️  Frontmost app is '{frontmost_name}', trying that instead"
                        )
                        frontmost_windows = self._get_app_windows(frontmost)
                        for window in frontmost_windows:
                            self._collect_interactive_elements(window, elements)

        except Exception as e:
            print(f"    ⚠️  Accessibility search error: {e}")
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

                print(f"    ✓ Got app reference: {getattr(app, 'AXTitle', 'Unknown')}")

                # Try to get windows from this app reference
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
                print(
                    f"    ❌ FAILED: App '{getattr(app, 'AXTitle', 'Unknown')}' has 0 windows after 3 retries!"
                )
                print(f"       hasattr AXWindows: {hasattr(app, 'AXWindows')}")
                print(f"       hasattr AXChildren: {hasattr(app, 'AXChildren')}")
                if hasattr(app, "AXWindows"):
                    print(f"       app.AXWindows value: {app.AXWindows}")
                if hasattr(app, "AXChildren"):
                    print(
                        f"       app.AXChildren count: {len(app.AXChildren) if app.AXChildren else 0}"
                    )

            # Collect menu bar elements
            if include_menu_bar and hasattr(app, "AXMenuBar"):
                try:
                    menu_bar = app.AXMenuBar
                    self._collect_all_elements(
                        menu_bar, categorized, depth=0, context="menu_bar"
                    )
                except Exception:
                    pass

            # Use the windows we found
            print(
                f"    Searching {len(windows)} window(s) for all UI elements (categorized)"
            )

            for window in windows:
                self._collect_all_elements(
                    window, categorized, depth=0, context="window"
                )

            # Fallback to frontmost app if no elements found
            if all(len(v) == 0 for v in categorized.values()) and len(windows) > 0:
                frontmost = self.atomacos.NativeUIElement.getFrontmostApp()
                if frontmost and hasattr(frontmost, "AXTitle"):
                    frontmost_name = str(frontmost.AXTitle)
                    if frontmost_name.lower() != (app_name or "").lower():
                        print(
                            f"    ⚠️  Frontmost app is '{frontmost_name}', trying that instead"
                        )
                        frontmost_windows = self._get_app_windows(frontmost)
                        for window in frontmost_windows:
                            self._collect_all_elements(
                                window, categorized, depth=0, context="window"
                            )

        except Exception as e:
            print(f"    ⚠️  Accessibility search error: {e}")

        # Print summary
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
            windows = self._get_app_windows(app)

            if windows:
                main_window = windows[0]
                if hasattr(main_window, "AXPosition") and hasattr(
                    main_window, "AXSize"
                ):
                    pos = main_window.AXPosition
                    size = main_window.AXSize
                    return (int(pos[0]), int(pos[1]), int(size[0]), int(size[1]))
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
            container: Accessibility element to traverse
            categorized: Dictionary to store categorized elements
            depth: Current recursion depth
            context: Context hint (menu_bar, window, etc.)
        """
        if depth > 25:
            return

        try:
            elem_role = getattr(container, "AXRole", "")
            role_str = str(elem_role)

            if role_str == "AXApplication":
                if hasattr(container, "AXChildren") and container.AXChildren:
                    for child in container.AXChildren:
                        self._collect_all_elements(
                            child, categorized, depth + 1, context
                        )
                return

            category = self._categorize_element(role_str, context)
            element_info = self._extract_element_info(container, role_str, category)

            if element_info:
                categorized[category].append(element_info)

            if hasattr(container, "AXChildren") and container.AXChildren:
                new_context = context
                if role_str in ["AXMenuBar", "AXMenuBarItem"]:
                    new_context = "menu_bar"
                elif role_str in ["AXMenu", "AXMenuItem"]:
                    new_context = "menu_items"

                for child in container.AXChildren:
                    self._collect_all_elements(
                        child, categorized, depth + 1, new_context
                    )

        except Exception:
            pass

    def _categorize_element(self, role_str: str, context: str) -> str:
        """
        Categorize an element based on its role and context.

        Returns:
            Category name: interactive, menu_bar, menu_items, static, or structural
        """
        if context == "menu_bar" or role_str in [
            "AXMenuBar",
            "AXMenuBarItem",
            "AXMenuButton",
        ]:
            return "menu_bar"

        if context == "menu_items" or role_str in ["AXMenu", "AXMenuItem"]:
            return "menu_items"

        interactive_roles = [
            "AXButton",
            "AXCheckBox",
            "AXRadioButton",
            "AXTextField",
            "AXTextArea",
            "AXComboBox",
            "AXPopUpButton",
            "AXSlider",
            "AXIncrementor",
            "AXLink",
            "AXTab",
            "AXSwitch",
            "AXToggle",
            "AXSearchField",
            "AXSecureTextField",
        ]
        if role_str in interactive_roles:
            return "interactive"

        static_roles = [
            "AXStaticText",
            "AXText",
            "AXLabel",
            "AXImage",
            "AXValueIndicator",
        ]
        if role_str in static_roles:
            return "static"

        structural_roles = [
            "AXGroup",
            "AXToolbar",
            "AXSplitGroup",
            "AXScrollArea",
            "AXList",
            "AXTable",
            "AXRow",
            "AXColumn",
            "AXOutline",
            "AXTabGroup",
        ]
        if role_str in structural_roles:
            return "structural"

        return "structural"

    def _extract_element_info(
        self, container, role_str: str, category: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract relevant information from an accessibility element.

        Returns:
            Dictionary with element info or None if element should be skipped
        """
        try:
            identifier = getattr(container, "AXIdentifier", "")
            description = ""

            if hasattr(container, "AXAttributedDescription"):
                try:
                    desc_obj = container.AXAttributedDescription
                    description = str(desc_obj).split("{")[0].strip()
                except Exception:
                    pass

            if not description:
                description = (
                    getattr(container, "AXTitle", "")
                    or getattr(container, "AXValue", "")
                    or getattr(container, "AXDescription", "")
                )

            if not identifier and not description:
                return None

            center = None
            bounds = None
            is_valid_for_clicking = True
            try:
                if hasattr(container, "AXPosition") and hasattr(container, "AXSize"):
                    position = container.AXPosition
                    size = container.AXSize
                    x, y = position
                    w, h = size

                    if w <= 0 or h <= 0:
                        is_valid_for_clicking = False
                    elif (
                        x < 0
                        or y < 0
                        or x > self.screen_width
                        or y > self.screen_height
                    ):
                        is_valid_for_clicking = False

                    if is_valid_for_clicking:
                        center = [int(x + w / 2), int(y + h / 2)]
                        bounds = [int(x), int(y), int(w), int(h)]

                        if y < 40 and category == "menu_bar":
                            is_valid_for_clicking = False
            except Exception:
                pass

            if not is_valid_for_clicking:
                return None

            return {
                "identifier": identifier,
                "role": role_str.replace("AX", ""),
                "description": str(description),
                "label": str(description),
                "title": str(description),
                "category": category,
                "center": center,
                "bounds": bounds,
                "has_actions": bool(
                    hasattr(container, "AXActions") and container.AXActions
                ),
                "enabled": bool(
                    hasattr(container, "AXEnabled") and container.AXEnabled
                ),
                "_element": container,
            }

        except Exception:
            return None

    def _collect_interactive_elements(
        self, container, elements: List[Dict[str, Any]], depth=0
    ):
        """Recursively collect interactive elements for LLM context."""
        if depth > 20:
            return

        try:
            elem_role = getattr(container, "AXRole", "")

            if str(elem_role) == "AXApplication":
                if hasattr(container, "AXChildren") and container.AXChildren:
                    for child in container.AXChildren:
                        self._collect_interactive_elements(child, elements, depth + 1)
                return

            is_interactive = False
            role_str = str(elem_role)

            if hasattr(container, "AXActions") and container.AXActions:
                is_interactive = True

            if not is_interactive and hasattr(container, "AXEnabled"):
                if container.AXEnabled:
                    interactive_roles = [
                        "AXButton",
                        "AXCheckBox",
                        "AXRadioButton",
                        "AXTextField",
                        "AXTextArea",
                        "AXComboBox",
                        "AXPopUpButton",
                        "AXSlider",
                        "AXIncrementor",
                        "AXLink",
                        "AXMenuItem",
                        "AXTab",
                    ]
                    if role_str in interactive_roles:
                        is_interactive = True

            if not is_interactive and role_str in [
                "AXButton",
                "AXCheckBox",
                "AXRadioButton",
            ]:
                is_interactive = True

            if is_interactive:
                identifier = getattr(container, "AXIdentifier", "")
                description = ""

                if hasattr(container, "AXAttributedDescription"):
                    try:
                        desc_obj = container.AXAttributedDescription
                        description = str(desc_obj).split("{")[0].strip()
                    except Exception:
                        pass

                if not description:
                    description = getattr(container, "AXTitle", "") or getattr(
                        container, "AXValue", ""
                    )

                if identifier or description:
                    try:
                        position = container.AXPosition
                        size = container.AXSize
                        x, y = position
                        w, h = size

                        elements.append(
                            {
                                "identifier": identifier,
                                "role": str(elem_role).replace("AX", ""),
                                "description": description,
                                "label": description,  # For compatibility with click_element
                                "title": description,  # For compatibility with click_element
                                "center": [int(x + w / 2), int(y + h / 2)],
                                "bounds": [int(x), int(y), int(w), int(h)],
                            }
                        )
                    except Exception:
                        # If we can't get coordinates, skip this element
                        pass

            if hasattr(container, "AXChildren") and container.AXChildren:
                for child in container.AXChildren:
                    self._collect_interactive_elements(child, elements, depth + 1)

        except Exception:
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
            role: Accessibility role
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

            console.print(
                f"    [dim]Searching {len(windows)} window(s) for '{label}'[/dim]"
            )

            for window in windows:
                self._traverse_and_collect(window, label, role, elements)

            if len(elements) == 0 and app_name:
                frontmost = self.atomacos.NativeUIElement.getFrontmostApp()
                if frontmost and hasattr(frontmost, "AXTitle"):
                    frontmost_name = str(frontmost.AXTitle)
                    if frontmost_name.lower() != app_name.lower():
                        console.print(
                            f"    [yellow]⚠️  Also checking frontmost app: {frontmost_name}[/yellow]"
                        )
                        frontmost_windows = self._get_app_windows(frontmost)
                        for window in frontmost_windows:
                            self._traverse_and_collect(window, label, role, elements)

            console.print(f"  [green]Found {len(elements)} elements[/green]")

        except Exception:
            pass

        return elements

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

        # Check cache first!
        if self.current_app_name and self.current_app_ref:
            if app_name.lower() == self.current_app_name.lower():
                print(f"        [_get_app] 🚀 Using CACHED reference for '{app_name}'")
                return self.current_app_ref

        # Try to get the app reference directly
        try:
            app = self.atomacos.getAppRefByLocalizedName(app_name)
            app_title = getattr(app, "AXTitle", "")
            print(f"        [_get_app] getAppRefByLocalizedName returned: {app_title}")

            # Verify the returned app actually matches what we requested
            if app_title and (
                app_name.lower() in app_title.lower()
                or app_title.lower() in app_name.lower()
            ):
                print(f"        [_get_app] ✅ App name matches, returning {app_title}")
                return app
            else:
                print(
                    f"        [_get_app] ❌ WRONG APP! Requested '{app_name}' but got '{app_title}'"
                )
                raise ValueError(
                    f"App name mismatch: requested '{app_name}', got '{app_title}'"
                )
        except Exception as e:
            print(f"        [_get_app] ❌ Failed to get app: {e}")

            # Try running applications list as final attempt (no frontmost fallback!)
            try:
                running_apps = self.atomacos.NativeUIElement.runningApplications()
                for app in running_apps:
                    if hasattr(app, "AXTitle"):
                        title = str(app.AXTitle)
                        if (
                            app_name.lower() in title.lower()
                            or title.lower() in app_name.lower()
                        ):
                            print(
                                f"        [_get_app] ✅ Found '{title}' in running apps"
                            )
                            return app
            except Exception:
                pass

            raise Exception(
                f"App '{app_name}' not found. Make sure it's opened with open_application first."
            )

    def get_text_from_app(self, app_name: str, role: Optional[str] = None) -> List[str]:
        """
        Extract all text values from an application using Accessibility API.
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
            elem_role = getattr(container, "AXRole", "")

            if role_filter and str(elem_role) != f"AX{role_filter}":
                pass
            else:
                if hasattr(container, "AXValue") and container.AXValue:
                    value = str(container.AXValue).strip()
                    if value and value not in texts:
                        texts.append(value)

                if hasattr(container, "AXTitle") and container.AXTitle:
                    title = str(container.AXTitle).strip()
                    if title and title not in texts:
                        texts.append(title)

            if hasattr(container, "AXChildren") and container.AXChildren:
                for child in container.AXChildren:
                    self._collect_text_values(child, texts, role_filter, depth + 1)

        except Exception:
            pass

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
            )
            apps_string = result.stdout.strip()
            app_names = [app.strip() for app in apps_string.split(",")]
            return app_names
        except Exception:
            return []

    def get_frontmost_app_name(self) -> Optional[str]:
        """
        Get the name of the frontmost (active) application using AppleScript.
        This is more reliable than atomacos as it ignores transient system UI.

        Returns:
            Name of frontmost app, or None if unavailable
        """
        if not self.available:
            return None

        try:
            import subprocess

            timing = get_timing_config()
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=timing.applescript_timeout,
            )
            app_name = result.stdout.strip()
            return app_name if app_name else None
        except Exception:
            return None

    def is_app_frontmost(self, app_name: str) -> bool:
        """
        Check if an application is currently the frontmost (active) app.
        Uses fuzzy matching to handle partial names and child windows.

        Args:
            app_name: Application name to check

        Returns:
            True if app or related windows are frontmost, False otherwise
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

    def _get_app_windows(self, app):
        """
        Get all windows for an application.
        Simple and fast - retries are handled at the app reference level.
        """
        if not app:
            print("      [_get_app_windows] app is None, returning []")
            return []

        app_title = getattr(app, "AXTitle", "Unknown")
        print(f"      [_get_app_windows] Checking '{app_title}'...")

        # Try AXWindows first (most common)
        has_ax_windows = hasattr(app, "AXWindows")
        print(f"      [_get_app_windows] hasattr(app, 'AXWindows'): {has_ax_windows}")

        if has_ax_windows:
            ax_windows_val = app.AXWindows
            print(
                f"      [_get_app_windows] app.AXWindows = {ax_windows_val} (type: {type(ax_windows_val)})"
            )
            if ax_windows_val:
                windows_list = list(ax_windows_val)
                print(
                    f"      [_get_app_windows] ✅ Returning {len(windows_list)} windows via AXWindows"
                )
                return windows_list
            else:
                print("      [_get_app_windows] app.AXWindows is falsy (empty or None)")

        # Fallback to AXChildren and filter for windows
        has_ax_children = hasattr(app, "AXChildren")
        print(f"      [_get_app_windows] hasattr(app, 'AXChildren'): {has_ax_children}")

        if has_ax_children:
            ax_children_val = app.AXChildren
            print(
                f"      [_get_app_windows] app.AXChildren count: {len(ax_children_val) if ax_children_val else 0}"
            )

            if ax_children_val:
                windows = [
                    child
                    for child in ax_children_val
                    if hasattr(child, "AXRole")
                    and str(child.AXRole) in ["AXWindow", "AXSheet", "AXDrawer"]
                ]
                print(
                    f"      [_get_app_windows] Found {len(windows)} window-like children"
                )
                if windows:
                    return windows

        print("      [_get_app_windows] ❌ Returning [] - no windows found")
        return []

    def _find_element(self, app, label: str, depth=0):
        """Recursively find element by label."""
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
        """Recursively search accessibility tree for element with target text."""
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

        except Exception:
            pass

        return None

    def _element_matches_text(self, element, target_text):
        """Check if element's text attributes match the target text. EXACT MATCH ONLY."""
        try:
            if hasattr(element, "AXIdentifier") and element.AXIdentifier:
                identifier = str(element.AXIdentifier).lower()
                if identifier == target_text:
                    return True

            if (
                hasattr(element, "AXAttributedDescription")
                and element.AXAttributedDescription
            ):
                try:
                    desc_str = str(element.AXAttributedDescription).lower()
                    if desc_str == target_text:
                        return True
                except Exception:
                    pass

            if hasattr(element, "AXTitle") and element.AXTitle:
                title = str(element.AXTitle).lower()
                if title == target_text:
                    return True

            if hasattr(element, "AXValue") and element.AXValue:
                value = str(element.AXValue).lower()
                if value == target_text:
                    return True

        except Exception:
            pass

        return False

    def _perform_click(self, element):
        """Perform click action on element using atomacos."""
        try:
            if hasattr(element, "Press"):
                element.Press()
                return True
            elif hasattr(element, "AXPress"):
                element.AXPress()
                return True
            else:
                raise Exception("Element does not support Press/AXPress action")
        except Exception as e:
            raise Exception(f"Click action failed: {str(e)}")

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
                except Exception:
                    pass

            if hasattr(container, "AXChildren") and container.AXChildren:
                for child in container.AXChildren:
                    self._traverse_and_collect(child, label, role, elements, depth + 1)

        except Exception:
            pass
