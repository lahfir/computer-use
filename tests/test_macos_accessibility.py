"""
Comprehensive tests for macOS Accessibility API.

Tests all public methods in MacOSAccessibility class.
"""

import platform
import pytest
from unittest.mock import MagicMock


SKIP_NON_DARWIN = pytest.mark.skipif(
    platform.system().lower() != "darwin",
    reason="macOS-only tests",
)


class TestMacOSAccessibilityInit:
    """Test initialization and availability checks."""

    @SKIP_NON_DARWIN
    def test_init_default_screen_size(self):
        """Test initialization with default screen size."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc.screen_width == 1920
        assert acc.screen_height == 1080

    @SKIP_NON_DARWIN
    def test_init_custom_screen_size(self):
        """Test initialization with custom screen size."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility(screen_width=2560, screen_height=1440)
        assert acc.screen_width == 2560
        assert acc.screen_height == 1440

    @SKIP_NON_DARWIN
    def test_availability_check(self):
        """Test that availability is properly detected."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert isinstance(acc.available, bool)

    @SKIP_NON_DARWIN
    def test_caches_initialized(self):
        """Test that caches are initialized as empty dicts."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc._app_cache == {}
        assert acc._element_cache == {}
        assert acc._element_registry == {}


class TestCacheManagement:
    """Test cache clearing and invalidation."""

    @SKIP_NON_DARWIN
    def test_clear_cache(self):
        """Test clear_cache clears app and element caches."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc._app_cache["test"] = "value"
        acc._element_cache["test"] = []

        acc.clear_cache()

        assert acc._app_cache == {}
        assert acc._element_cache == {}

    @SKIP_NON_DARWIN
    def test_invalidate_cache(self):
        """Test invalidate_cache clears element cache and registry."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc._element_cache["test"] = []
        acc._element_registry["test"] = {}

        acc.invalidate_cache()

        assert acc._element_cache == {}
        assert acc._element_registry == {}
        assert acc._last_interaction_time > 0

    @SKIP_NON_DARWIN
    def test_clear_app_cache_alias(self):
        """Test clear_app_cache is an alias for clear_cache."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc._app_cache["test"] = "value"

        acc.clear_app_cache()

        assert acc._app_cache == {}


class TestAppManagement:
    """Test application lookup and management."""

    @SKIP_NON_DARWIN
    def test_get_app_empty_name(self):
        """Test get_app returns None for empty name."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc.get_app("") is None
        assert acc.get_app(None) is None

    @SKIP_NON_DARWIN
    def test_get_app_not_available(self):
        """Test get_app returns None when not available."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False
        assert acc.get_app("Finder") is None

    @SKIP_NON_DARWIN
    def test_get_app_uses_cache(self):
        """Test get_app uses cache for repeated lookups."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        mock_app = MagicMock()
        acc._app_cache["finder"] = mock_app

        result = acc.get_app("Finder")
        assert result == mock_app

    @SKIP_NON_DARWIN
    def test_set_active_app_clears_element_cache(self):
        """Test set_active_app clears element cache."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc._element_cache["test"] = []

        acc.set_active_app("Finder")

        assert acc._element_cache == {}

    @SKIP_NON_DARWIN
    def test_is_app_running(self):
        """Test is_app_running returns bool."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.is_app_running("Finder")
        assert isinstance(result, bool)

    @SKIP_NON_DARWIN
    def test_get_running_apps(self):
        """Test get_running_apps returns list of strings."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        apps = acc.get_running_apps()
        assert isinstance(apps, list)

    @SKIP_NON_DARWIN
    def test_get_running_app_names_alias(self):
        """Test get_running_app_names is alias for get_running_apps."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result1 = acc.get_running_apps()
        result2 = acc.get_running_app_names()
        assert result1 == result2

    @SKIP_NON_DARWIN
    def test_get_frontmost_app(self):
        """Test get_frontmost_app returns string or None."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.get_frontmost_app()
        assert result is None or isinstance(result, str)

    @SKIP_NON_DARWIN
    def test_get_frontmost_app_name_alias(self):
        """Test get_frontmost_app_name is alias."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        result1 = acc.get_frontmost_app()
        result2 = acc.get_frontmost_app_name()
        assert result1 == result2

    @SKIP_NON_DARWIN
    def test_is_app_frontmost(self):
        """Test is_app_frontmost returns bool."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.is_app_frontmost("Finder")
        assert isinstance(result, bool)


class TestWindowManagement:
    """Test window-related methods."""

    @SKIP_NON_DARWIN
    def test_get_windows_none_app(self):
        """Test get_windows returns empty list for None app."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc.get_windows(None) == []

    @SKIP_NON_DARWIN
    def test_get_window_bounds(self):
        """Test get_window_bounds returns tuple or None."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.get_window_bounds("Finder")
        assert result is None or (isinstance(result, tuple) and len(result) == 4)

    @SKIP_NON_DARWIN
    def test_get_app_window_bounds_alias(self):
        """Test get_app_window_bounds is alias."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.get_app_window_bounds("Finder")
        assert result is None or isinstance(result, tuple)

    @SKIP_NON_DARWIN
    def test_get_app_window_bounds_none(self):
        """Test get_app_window_bounds with None returns None."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc.get_app_window_bounds(None) is None


class TestElementDiscovery:
    """Test element discovery and traversal."""

    @SKIP_NON_DARWIN
    def test_get_elements_not_available(self):
        """Test get_elements returns empty list when not available."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False
        assert acc.get_elements("Finder") == []

    @SKIP_NON_DARWIN
    def test_get_elements_uses_cache(self):
        """Test get_elements uses cache when available."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        cached_elements = [{"element_id": "test", "label": "Test"}]
        acc._element_cache["finder:True"] = cached_elements

        result = acc.get_elements("Finder", use_cache=True)
        assert result == cached_elements

    @SKIP_NON_DARWIN
    def test_get_elements_bypasses_cache(self):
        """Test get_elements bypasses cache when use_cache=False."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        cached_elements = [{"element_id": "cached", "label": "Cached"}]
        acc._element_cache["finder:True"] = cached_elements

        result = acc.get_elements("Finder", interactive_only=True, use_cache=False)
        assert result != cached_elements or result == []

    @SKIP_NON_DARWIN
    def test_get_all_interactive_elements(self):
        """Test get_all_interactive_elements returns list."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.get_all_interactive_elements("Finder")
        assert isinstance(result, list)

    @SKIP_NON_DARWIN
    def test_get_all_interactive_elements_none(self):
        """Test get_all_interactive_elements with None returns empty list."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc.get_all_interactive_elements(None) == []

    @SKIP_NON_DARWIN
    def test_get_all_ui_elements(self):
        """Test get_all_ui_elements returns categorized dict."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.get_all_ui_elements("Finder")
        assert isinstance(result, dict)
        assert "interactive" in result
        assert "menu_bar" in result
        assert "menu_items" in result
        assert "static" in result
        assert "structural" in result

    @SKIP_NON_DARWIN
    def test_get_all_ui_elements_none(self):
        """Test get_all_ui_elements with None returns empty categories."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        result = acc.get_all_ui_elements(None)
        assert all(v == [] for v in result.values())


class TestElementRegistry:
    """Test element registry pattern."""

    @SKIP_NON_DARWIN
    def test_get_element_by_id(self):
        """Test get_element_by_id retrieves from registry."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        test_element = {"element_id": "abc123", "label": "Test"}
        acc._element_registry["abc123"] = test_element

        result = acc.get_element_by_id("abc123")
        assert result == test_element

    @SKIP_NON_DARWIN
    def test_get_element_by_id_not_found(self):
        """Test get_element_by_id returns None for unknown ID."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        result = acc.get_element_by_id("nonexistent")
        assert result is None


class TestElementSearch:
    """Test element search methods."""

    @SKIP_NON_DARWIN
    def test_find_element(self):
        """Test find_element searches by label."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.find_element("Finder", "File")
        assert result is None or isinstance(result, dict)

    @SKIP_NON_DARWIN
    def test_find_element_exact_match(self):
        """Test find_element with exact_match flag."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.find_element("Finder", "File", exact_match=True)
        assert result is None or isinstance(result, dict)

    @SKIP_NON_DARWIN
    def test_find_elements(self):
        """Test find_elements with label and role filters."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.find_elements(label="File", app_name="Finder")
        assert isinstance(result, list)

    @SKIP_NON_DARWIN
    def test_find_elements_no_app_name(self):
        """Test find_elements returns empty without app_name."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc.find_elements(label="Test") == []


class TestClickMethods:
    """Test click-related methods."""

    @SKIP_NON_DARWIN
    def test_click_by_id_not_available(self):
        """Test click_by_id returns failure when not available."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False

        success, msg = acc.click_by_id("test")
        assert success is False
        assert "not available" in msg.lower()

    @SKIP_NON_DARWIN
    def test_click_by_id_not_found(self):
        """Test click_by_id returns failure for unknown ID."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        success, msg = acc.click_by_id("nonexistent")
        assert success is False
        assert "not found" in msg.lower()

    @SKIP_NON_DARWIN
    def test_click_element(self):
        """Test click_element returns tuple."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        success, element = acc.click_element("NonexistentLabel12345", "Finder")
        assert isinstance(success, bool)

    @SKIP_NON_DARWIN
    def test_click_element_not_available(self):
        """Test click_element returns failure when not available."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False

        success, element = acc.click_element("Test", "Finder")
        assert success is False
        assert element is None

    @SKIP_NON_DARWIN
    def test_click_element_or_parent(self):
        """Test click_element_or_parent returns tuple."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False

        success, method = acc.click_element_or_parent({"label": "test"})
        assert success is False
        assert method == "unavailable"

    @SKIP_NON_DARWIN
    def test_click_element_or_parent_no_reference(self):
        """Test click_element_or_parent with no _element reference."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        success, method = acc.click_element_or_parent({"label": "test"})
        assert success is False
        assert method == "no_reference"

    @SKIP_NON_DARWIN
    def test_try_click_element_or_parent_alias(self):
        """Test try_click_element_or_parent is alias."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False

        result1 = acc.click_element_or_parent({"label": "test"})
        result2 = acc.try_click_element_or_parent({"label": "test"})
        assert result1 == result2


class TestTextExtraction:
    """Test text extraction methods."""

    @SKIP_NON_DARWIN
    def test_get_text_not_available(self):
        """Test get_text returns empty list when not available."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False
        assert acc.get_text("Finder") == []

    @SKIP_NON_DARWIN
    def test_get_text(self):
        """Test get_text returns list of strings."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        if not acc.available:
            pytest.skip("Accessibility not available")

        result = acc.get_text("Finder")
        assert isinstance(result, list)

    @SKIP_NON_DARWIN
    def test_get_text_from_app_alias(self):
        """Test get_text_from_app is alias."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        acc.available = False

        result = acc.get_text_from_app("Finder")
        assert result == []


class TestNameMatching:
    """Test internal name matching logic."""

    @SKIP_NON_DARWIN
    def test_matches_name_case_insensitive(self):
        """Test _matches_name is case-insensitive."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc._matches_name("Finder", "finder")
        assert acc._matches_name("FINDER", "finder")

    @SKIP_NON_DARWIN
    def test_matches_name_partial(self):
        """Test _matches_name allows partial matches."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert acc._matches_name("System Settings", "Settings")
        assert acc._matches_name("Settings", "System Settings")

    @SKIP_NON_DARWIN
    def test_matches_name_empty(self):
        """Test _matches_name returns False for empty strings."""
        from computer_use.tools.accessibility.macos_accessibility import (
            MacOSAccessibility,
        )

        acc = MacOSAccessibility()
        assert not acc._matches_name("", "Finder")
        assert not acc._matches_name("Finder", "")
        assert not acc._matches_name("", "")
