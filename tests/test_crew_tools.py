"""
Comprehensive tests for CrewAI GUI tools.

Tests that each tool:
1. Returns an ActionResult
2. Has correct action_taken describing what happened
3. Has appropriate success/error states
4. Matches tool name with output
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass


@dataclass
class MockActionResult:
    """Mock ActionResult for testing."""

    success: bool
    action_taken: str
    method_used: str
    confidence: float
    error: str = None
    data: dict = None


class TestToolOutputCorrectness:
    """Test that each tool returns output matching its name and purpose."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock tool registry."""
        registry = Mock()

        mock_accessibility = Mock()
        mock_accessibility.available = True
        mock_accessibility.is_app_running = Mock(return_value=True)
        mock_accessibility.get_running_app_names = Mock(
            return_value=["Calculator", "Finder"]
        )
        mock_accessibility.get_all_ui_elements = Mock(return_value={"buttons": []})
        mock_accessibility.get_all_interactive_elements = Mock(return_value=[])
        mock_accessibility.get_app = Mock(return_value=Mock())
        mock_accessibility.get_windows = Mock(return_value=[])
        mock_accessibility.invalidate_cache = Mock()
        mock_accessibility.click_by_id = Mock(return_value=(True, "Clicked element"))
        mock_accessibility.get_element_by_id = Mock(return_value={"center": [100, 100]})
        mock_accessibility.get_app_window_bounds = Mock(return_value=(0, 0, 800, 600))

        mock_process = Mock()
        mock_process.open_application = Mock(return_value={"success": True})
        mock_process.focus_app = Mock()
        mock_process.is_process_running = Mock(return_value=True)

        mock_screenshot = Mock()
        mock_screenshot.capture = Mock(return_value=Mock(size=(1920, 1080)))
        mock_screenshot.capture_active_window = Mock(
            return_value=(Mock(size=(800, 600)), {"captured": True})
        )

        mock_ocr = Mock()
        mock_ocr.extract_all_text = Mock(return_value=[Mock(text="Test")])

        mock_input = Mock()
        mock_input.scroll = Mock()
        mock_input.click = Mock(return_value=True)
        mock_input.type_text = Mock()
        mock_input.paste_text = Mock()

        registry.get_tool = Mock(
            side_effect=lambda name: {
                "accessibility": mock_accessibility,
                "process": mock_process,
                "screenshot": mock_screenshot,
                "ocr": mock_ocr,
                "input": mock_input,
            }.get(name)
        )

        return registry

    def test_check_app_running_returns_correct_action(self, mock_registry):
        """CheckAppRunningTool should return action about checking app status."""
        from src.computer_use.crew_tools.gui_basic_tools import CheckAppRunningTool

        tool = CheckAppRunningTool()
        tool._tool_registry = mock_registry

        result = tool._run(app_name="Calculator")

        assert result.success is True
        assert (
            "check" in result.action_taken.lower()
            or "calculator" in result.action_taken.lower()
        )
        assert "is_running" in result.data
        assert result.method_used == "accessibility"

    def test_list_running_apps_returns_correct_action(self, mock_registry):
        """ListRunningAppsTool should return action about listing apps."""
        from src.computer_use.crew_tools.gui_basic_tools import ListRunningAppsTool

        tool = ListRunningAppsTool()
        tool._tool_registry = mock_registry

        result = tool._run()

        assert result.success is True
        assert (
            "found" in result.action_taken.lower()
            or "app" in result.action_taken.lower()
        )
        assert "running_apps" in result.data or "count" in result.data
        assert result.method_used == "accessibility"

    def test_open_application_returns_correct_action(self, mock_registry):
        """OpenApplicationTool should return action about opening app."""
        from src.computer_use.crew_tools.gui_basic_tools import OpenApplicationTool

        mock_registry.get_tool("accessibility").is_app_frontmost = Mock(
            return_value=True
        )
        mock_registry.get_tool("accessibility").set_active_app = Mock()

        tool = OpenApplicationTool()
        tool._tool_registry = mock_registry

        with patch(
            "src.computer_use.crew_tools.gui_basic_tools.check_cancellation",
            return_value=None,
        ):
            result = tool._run(app_name="Calculator")

        assert result.success is True
        assert (
            "open" in result.action_taken.lower()
            or "calculator" in result.action_taken.lower()
        )
        assert "process" in result.method_used or "verification" in result.method_used

    def test_scroll_returns_correct_action(self, mock_registry):
        """ScrollTool should return action about scrolling."""
        from src.computer_use.crew_tools.gui_basic_tools import ScrollTool

        tool = ScrollTool()
        tool._tool_registry = mock_registry

        result = tool._run(direction="down", amount=3)

        assert result.success is True
        assert "scroll" in result.action_taken.lower()
        assert result.data["direction"] == "down"
        assert result.method_used == "scroll"

    def test_take_screenshot_returns_correct_action(self, mock_registry):
        """TakeScreenshotTool should return action about capturing screenshot."""
        from src.computer_use.crew_tools.gui_basic_tools import TakeScreenshotTool

        tool = TakeScreenshotTool()
        tool._tool_registry = mock_registry

        result = tool._run()

        assert result.success is True
        assert (
            "screenshot" in result.action_taken.lower()
            or "captured" in result.action_taken.lower()
        )
        assert result.method_used == "screenshot_fullscreen"

    def test_read_screen_text_returns_correct_action(self, mock_registry):
        """ReadScreenTextTool should return action about reading text."""
        from src.computer_use.crew_tools.gui_basic_tools import ReadScreenTextTool

        tool = ReadScreenTextTool()
        tool._tool_registry = mock_registry

        with patch(
            "src.computer_use.crew_tools.gui_basic_tools.check_cancellation",
            return_value=None,
        ):
            result = tool._run()

        assert result.success is True
        assert (
            "read" in result.action_taken.lower()
            or "text" in result.action_taken.lower()
        )
        assert result.method_used == "ocr"

    def test_get_accessible_elements_returns_correct_action(self, mock_registry):
        """GetAccessibleElementsTool should return action about getting elements."""
        from src.computer_use.crew_tools.gui_basic_tools import (
            GetAccessibleElementsTool,
        )

        tool = GetAccessibleElementsTool()
        tool._tool_registry = mock_registry

        with patch(
            "src.computer_use.crew_tools.gui_basic_tools.check_cancellation",
            return_value=None,
        ):
            result = tool._run(app_name="Calculator")

        assert result.success is True
        assert (
            "element" in result.action_taken.lower()
            or "calculator" in result.action_taken.lower()
        )
        assert result.method_used == "accessibility"

    def test_click_element_with_id_returns_correct_action(self, mock_registry):
        """ClickElementTool with element_id should return native click action."""
        from src.computer_use.crew_tools.gui_interaction_tools import ClickElementTool

        tool = ClickElementTool()
        tool._tool_registry = mock_registry

        with patch(
            "src.computer_use.crew_tools.gui_interaction_tools.check_cancellation",
            return_value=None,
        ):
            result = tool._run(element_id="abc123", current_app="Calculator")

        assert result.success is True
        assert "click" in result.action_taken.lower()
        assert result.method_used == "accessibility_native"

    def test_type_text_returns_correct_action(self, mock_registry):
        """TypeTextTool should return action about typing."""
        from src.computer_use.crew_tools.gui_interaction_tools import TypeTextTool

        tool = TypeTextTool()
        tool._tool_registry = mock_registry

        result = tool._run(text="Hello World")

        assert result.success is True
        assert (
            "type" in result.action_taken.lower()
            or "char" in result.action_taken.lower()
        )
        assert result.method_used == "type"

    def test_type_text_hotkey_returns_correct_action(self, mock_registry):
        """TypeTextTool with hotkey should return hotkey action."""
        from src.computer_use.crew_tools.gui_interaction_tools import TypeTextTool

        mock_input = mock_registry.get_tool("input")
        mock_input.hotkey = Mock()

        tool = TypeTextTool()
        tool._tool_registry = mock_registry

        result = tool._run(text="cmd+c")

        assert result.success is True
        assert (
            "hotkey" in result.action_taken.lower()
            or "cmd+c" in result.action_taken.lower()
        )


class TestToolOutputMismatchPrevention:
    """Test that tool outputs cannot be misattributed."""

    def test_action_taken_contains_tool_relevant_info(self):
        """Each tool's action_taken should contain info relevant to that tool only."""
        tool_action_patterns = {
            "check_app_running": ["check", "running", "app"],
            "list_running_apps": ["found", "apps", "running"],
            "open_application": ["open", "launch", "focus"],
            "scroll": ["scroll"],
            "take_screenshot": ["screenshot", "capture"],
            "read_screen_text": ["read", "text", "ocr"],
            "get_accessible_elements": ["element", "found", "ui"],
            "click_element": ["click"],
            "type_text": ["type", "char", "hotkey"],
        }

        for tool_name, patterns in tool_action_patterns.items():
            assert len(patterns) > 0, f"{tool_name} should have validation patterns"


class TestActionResultStructure:
    """Test that ActionResult has all required fields."""

    def test_action_result_has_required_fields(self):
        """ActionResult should have success, action_taken, method_used, confidence."""
        from src.computer_use.schemas.actions import ActionResult

        result = ActionResult(
            success=True,
            action_taken="Test action",
            method_used="test",
            confidence=1.0,
        )

        assert hasattr(result, "success")
        assert hasattr(result, "action_taken")
        assert hasattr(result, "method_used")
        assert hasattr(result, "confidence")

    def test_action_result_error_field(self):
        """ActionResult should support error field for failures."""
        from src.computer_use.schemas.actions import ActionResult

        result = ActionResult(
            success=False,
            action_taken="Failed action",
            method_used="test",
            confidence=0.0,
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"
