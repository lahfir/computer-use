"""
Cross-platform accessibility API consistency tests.

Ensures all accessibility implementations (macOS, Windows, Linux)
have consistent method signatures for cross-platform compatibility.
"""

import inspect
from typing import Set, Dict
import pytest


def get_public_methods(cls) -> Dict[str, inspect.Signature]:
    """
    Get all public methods and their signatures from a class.

    Args:
        cls: Class to inspect

    Returns:
        Dict mapping method name to signature
    """
    methods = {}
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("_"):
            methods[name] = inspect.signature(method)
    return methods


def get_method_names(cls) -> Set[str]:
    """
    Get names of all public methods from a class.

    Args:
        cls: Class to inspect

    Returns:
        Set of method names
    """
    return {
        name
        for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


class TestCrossPlatformConsistency:
    """Verify all platform accessibility classes have consistent APIs."""

    def test_all_platforms_have_same_method_names(self):
        """Test that all platforms implement the same public methods."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        macos_methods = get_method_names(MacOSAccessibility)
        linux_methods = get_method_names(LinuxAccessibility)
        windows_methods = get_method_names(WindowsAccessibility)

        all_methods = macos_methods | linux_methods | windows_methods

        missing_report = []

        for method in sorted(all_methods):
            in_macos = method in macos_methods
            in_linux = method in linux_methods
            in_windows = method in windows_methods

            if not (in_macos and in_linux and in_windows):
                missing = []
                if not in_macos:
                    missing.append("macOS")
                if not in_linux:
                    missing.append("Linux")
                if not in_windows:
                    missing.append("Windows")
                missing_report.append(f"  {method}: missing in {', '.join(missing)}")

        if missing_report:
            report = "\n".join(missing_report)
            pytest.fail(
                f"\nMethod name inconsistencies across platforms:\n{report}\n\n"
                f"All platforms should implement the same public methods."
            )

    def test_core_methods_exist_on_all_platforms(self):
        """Test that essential methods exist on all platforms."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        core_methods = [
            "get_app",
            "get_windows",
            "get_elements",
            "get_element_by_id",
            "click_by_id",
            "click_element",
            "click_element_or_parent",
            "find_element",
            "find_elements",
            "get_text",
            "get_window_bounds",
            "is_app_running",
            "get_running_apps",
            "get_frontmost_app",
            "is_app_frontmost",
            "clear_cache",
            "invalidate_cache",
            "set_active_app",
            "get_all_ui_elements",
            "get_all_interactive_elements",
        ]

        platforms = {
            "macOS": MacOSAccessibility,
            "Linux": LinuxAccessibility,
            "Windows": WindowsAccessibility,
        }

        missing = []
        for platform_name, cls in platforms.items():
            methods = get_method_names(cls)
            for method in core_methods:
                if method not in methods:
                    missing.append(f"  {platform_name}: missing {method}")

        if missing:
            report = "\n".join(missing)
            pytest.fail(
                f"\nCore methods missing from platforms:\n{report}\n\n"
                f"These methods are essential for cross-platform operation."
            )

    def test_backward_compatible_aliases_exist(self):
        """Test that backward-compatible method aliases exist."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        alias_methods = [
            "try_click_element_or_parent",
            "get_text_from_app",
            "get_app_window_bounds",
            "get_running_app_names",
            "get_frontmost_app_name",
            "clear_app_cache",
        ]

        platforms = {
            "macOS": MacOSAccessibility,
            "Linux": LinuxAccessibility,
            "Windows": WindowsAccessibility,
        }

        missing = []
        for platform_name, cls in platforms.items():
            methods = get_method_names(cls)
            for method in alias_methods:
                if method not in methods:
                    missing.append(f"  {platform_name}: missing alias {method}")

        if missing:
            report = "\n".join(missing)
            pytest.fail(
                f"\nBackward-compatible aliases missing:\n{report}\n\n"
                f"These aliases ensure old code continues to work."
            )

    def test_method_parameter_counts_match(self):
        """Test that methods have same parameter counts across platforms."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        methods_to_check = [
            "get_app",
            "get_elements",
            "click_by_id",
            "find_element",
            "get_text",
            "is_app_running",
        ]

        platforms = {
            "macOS": MacOSAccessibility,
            "Linux": LinuxAccessibility,
            "Windows": WindowsAccessibility,
        }

        param_counts: Dict[str, Dict[str, int]] = {}

        for method_name in methods_to_check:
            param_counts[method_name] = {}
            for platform_name, cls in platforms.items():
                methods = get_public_methods(cls)
                if method_name in methods:
                    sig = methods[method_name]
                    param_counts[method_name][platform_name] = len(sig.parameters)

        mismatches = []
        for method_name, counts in param_counts.items():
            if len(set(counts.values())) > 1:
                details = ", ".join(f"{p}: {c}" for p, c in counts.items())
                mismatches.append(f"  {method_name}: {details}")

        if mismatches:
            report = "\n".join(mismatches)
            pytest.fail(
                f"\nParameter count mismatches:\n{report}\n\n"
                f"Methods should have same parameter counts across platforms."
            )

    def test_return_type_consistency(self):
        """Test that key methods return consistent types."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        platforms = [
            ("macOS", MacOSAccessibility(screen_width=1920, screen_height=1080)),
            ("Linux", LinuxAccessibility(screen_width=1920, screen_height=1080)),
            ("Windows", WindowsAccessibility(screen_width=1920, screen_height=1080)),
        ]

        for platform_name, acc in platforms:
            acc.available = False

            assert acc.get_app("Test") is None, (
                f"{platform_name}: get_app should return None"
            )
            assert acc.get_windows(None) == [], (
                f"{platform_name}: get_windows should return []"
            )
            assert acc.get_elements("Test") == [], (
                f"{platform_name}: get_elements should return []"
            )
            assert acc.get_running_apps() == [], (
                f"{platform_name}: get_running_apps should return []"
            )
            assert acc.get_text("Test") == [], (
                f"{platform_name}: get_text should return []"
            )
            assert acc.is_app_running("Test") is False, (
                f"{platform_name}: is_app_running should return False"
            )

    def test_click_by_id_returns_tuple(self):
        """Test that click_by_id returns (bool, str) tuple on all platforms."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        platforms = [
            ("macOS", MacOSAccessibility(screen_width=1920, screen_height=1080)),
            ("Linux", LinuxAccessibility(screen_width=1920, screen_height=1080)),
            ("Windows", WindowsAccessibility(screen_width=1920, screen_height=1080)),
        ]

        for platform_name, acc in platforms:
            acc.available = False
            result = acc.click_by_id("test")

            assert isinstance(result, tuple), f"{platform_name}: should return tuple"
            assert len(result) == 2, f"{platform_name}: should return 2-tuple"
            assert isinstance(result[0], bool), (
                f"{platform_name}: first element should be bool"
            )
            assert isinstance(result[1], str), (
                f"{platform_name}: second element should be str"
            )

    def test_element_dict_structure(self):
        """Test that element dicts have consistent structure."""
        expected_keys = {
            "element_id",
            "identifier",
            "role",
            "label",
            "title",
            "description",
            "center",
            "bounds",
            "has_actions",
            "enabled",
            "_element",
        }

        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()

        test_element = {
            "element_id": "abc123",
            "identifier": "test_id",
            "role": "Button",
            "label": "Test Button",
            "title": "Test Button",
            "description": "A test button",
            "center": [100, 100],
            "bounds": [50, 50, 100, 50],
            "has_actions": True,
            "enabled": True,
            "_element": None,
        }

        acc._element_registry["abc123"] = test_element
        retrieved = acc.get_element_by_id("abc123")

        assert set(retrieved.keys()) == expected_keys, (
            f"Element dict should have keys: {expected_keys}\n"
            f"Got: {set(retrieved.keys())}"
        )


class TestPlatformSpecificBehavior:
    """Test platform-specific behavior is properly isolated."""

    def test_macos_uses_atomacos(self):
        """Test macOS implementation uses atomacos."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert hasattr(acc, "atomacos"), "macOS should have atomacos attribute"

    def test_linux_uses_pyatspi(self):
        """Test Linux implementation uses pyatspi."""
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )

        acc = LinuxAccessibility()
        assert hasattr(acc, "pyatspi"), "Linux should have pyatspi attribute"
        assert hasattr(acc, "desktop"), "Linux should have desktop attribute"

    def test_windows_uses_pywinauto(self):
        """Test Windows implementation uses pywinauto."""
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        acc = WindowsAccessibility()
        assert hasattr(acc, "pywinauto"), "Windows should have pywinauto attribute"
        assert hasattr(acc, "Desktop"), "Windows should have Desktop attribute"


class TestInitializationConsistency:
    """Test constructor parameters are consistent."""

    def test_all_accept_screen_dimensions(self):
        """Test all platforms accept screen_width and screen_height."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        width, height = 2560, 1440

        macos = MacOSAccessibility(screen_width=width, screen_height=height)
        linux = LinuxAccessibility(screen_width=width, screen_height=height)
        windows = WindowsAccessibility(screen_width=width, screen_height=height)

        assert macos.screen_width == width
        assert macos.screen_height == height
        assert linux.screen_width == width
        assert linux.screen_height == height
        assert windows.screen_width == width
        assert windows.screen_height == height

    def test_all_have_available_attribute(self):
        """Test all platforms have an 'available' attribute."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        macos = MacOSAccessibility()
        linux = LinuxAccessibility()
        windows = WindowsAccessibility()

        assert hasattr(macos, "available")
        assert hasattr(linux, "available")
        assert hasattr(windows, "available")
        assert isinstance(macos.available, bool)
        assert isinstance(linux.available, bool)
        assert isinstance(windows.available, bool)

    def test_all_have_cache_attributes(self):
        """Test all platforms have cache dictionaries."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )
        from computer_use.tools.accessibility.linux_accessibility import (
            LinuxAccessibility,
        )
        from computer_use.tools.accessibility.windows_accessibility import (
            WindowsAccessibility,
        )

        for cls in [MacOSAccessibility, LinuxAccessibility, WindowsAccessibility]:
            acc = cls()
            assert hasattr(acc, "_app_cache"), f"{cls.__name__} missing _app_cache"
            assert hasattr(acc, "_element_cache"), (
                f"{cls.__name__} missing _element_cache"
            )
            assert hasattr(acc, "_element_registry"), (
                f"{cls.__name__} missing _element_registry"
            )
