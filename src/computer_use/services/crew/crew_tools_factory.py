"""
Tool initialization factory for CrewAI crew.

Handles creation and configuration of all tools used by agents.
"""

from typing import Any, Dict

from ...config.llm_config import LLMConfig


class CrewToolsFactory:
    """
    Factory for creating and configuring crew tools.
    """

    @staticmethod
    def create_gui_tools(tool_registry: Any) -> Dict[str, Any]:
        """
        Create GUI interaction tools.

        Args:
            tool_registry: Platform tool registry instance

        Returns:
            Dictionary of tool name to tool instance
        """
        from ...crew_tools.gui_basic_tools import (
            CheckAppRunningTool,
            GetAccessibleElementsTool,
            GetWindowImageTool,
            ListRunningAppsTool,
            OpenApplicationTool,
            ReadScreenTextTool,
            RequestHumanInputTool,
            ScrollTool,
            SearchElementsTool,
            TakeScreenshotTool,
        )
        from ...crew_tools.gui_interaction_tools import (
            ClickElementTool,
            TypeTextTool,
        )
        from ...crew_tools.capability_tools import FindApplicationTool
        from ...crew_tools.analyze_image_tool import AnalyzeImageTool

        tools = {
            "take_screenshot": TakeScreenshotTool(),
            "click_element": ClickElementTool(),
            "type_text": TypeTextTool(),
            "open_application": OpenApplicationTool(),
            "read_screen_text": ReadScreenTextTool(),
            "scroll": ScrollTool(),
            "list_running_apps": ListRunningAppsTool(),
            "check_app_running": CheckAppRunningTool(),
            "get_accessible_elements": GetAccessibleElementsTool(),
            "get_window_image": GetWindowImageTool(),
            "find_application": FindApplicationTool(),
            "search_elements": SearchElementsTool(),
            "request_human_input": RequestHumanInputTool(),
            "analyze_image": AnalyzeImageTool(),
        }
        for tool in tools.values():
            try:
                tool._tool_registry = tool_registry
            except (AttributeError, ValueError):
                pass
        tools["find_application"]._llm = LLMConfig.get_orchestration_llm()
        return tools

    @staticmethod
    def create_observation_tools(tool_registry: Any) -> Dict[str, Any]:
        """
        Create observation tools.

        Args:
            tool_registry: Platform tool registry instance

        Returns:
            Dictionary of tool name to tool instance
        """
        from ...crew_tools.observation_tools import GetSystemStateTool

        tools = {
            "get_system_state": GetSystemStateTool(),
        }
        for tool in tools.values():
            tool._tool_registry = tool_registry
        return tools

    @staticmethod
    def create_web_tool(browser_agent: Any):
        """
        Create web automation tool.

        Args:
            browser_agent: Browser agent instance

        Returns:
            Configured WebAutomationTool
        """
        from ...crew_tools.web_tools import WebAutomationTool

        tool = WebAutomationTool()
        tool._browser_agent = browser_agent
        return tool

    @staticmethod
    def create_coding_tool(coding_agent: Any):
        """
        Create coding automation tool.

        Args:
            coding_agent: Coding agent instance

        Returns:
            Configured CodingAgentTool
        """
        from ...crew_tools.coding_tools import CodingAgentTool

        tool = CodingAgentTool()
        tool._coding_agent = coding_agent
        return tool

    @staticmethod
    def create_system_tool(safety_checker: Any, confirmation_manager: Any):
        """
        Create system command execution tool.

        Args:
            safety_checker: Safety checker instance
            confirmation_manager: Confirmation manager instance

        Returns:
            Configured ExecuteShellCommandTool
        """
        from ...crew_tools.system_tools import ExecuteShellCommandTool

        tool = ExecuteShellCommandTool()
        tool._safety_checker = safety_checker
        tool._confirmation_manager = confirmation_manager
        return tool
