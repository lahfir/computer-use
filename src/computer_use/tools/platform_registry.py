"""
Platform-aware tool registry for dynamic tool serving.
Uses parallel initialization for faster startup.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Union

from .system import FileTool, InputTool, ProcessTool, ScreenshotTool
from .accessibility import (
    MacOSAccessibility,
    WindowsAccessibility,
    LinuxAccessibility,
)
from .vision.ocr_tool import OCRTool
from ..schemas.tool_types import CapabilitiesSummary
from ..utils.platform import PlatformCapabilities
from ..utils.validation import CoordinateValidator, SafetyChecker

ToolType = Union[
    ScreenshotTool,
    InputTool,
    ProcessTool,
    FileTool,
    MacOSAccessibility,
    WindowsAccessibility,
    LinuxAccessibility,
    OCRTool,
]


class PlatformToolRegistry:
    """
    Dynamically loads and serves tools based on detected platform capabilities.
    """

    def __init__(
        self,
        capabilities: PlatformCapabilities,
        safety_checker: Optional[SafetyChecker] = None,
        coordinate_validator: Optional[CoordinateValidator] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        """
        Initialize tool registry with platform capabilities.

        Args:
            capabilities: PlatformCapabilities object
            safety_checker: Optional SafetyChecker instance
            coordinate_validator: Optional CoordinateValidator instance
            llm_client: Optional LLM client for browser agent
        """
        self.capabilities: PlatformCapabilities = capabilities
        self.safety_checker: Optional[SafetyChecker] = safety_checker
        self.coordinate_validator: Optional[CoordinateValidator] = coordinate_validator
        self.llm_client: Optional[Any] = llm_client
        self.tools: Dict[str, ToolType] = self._initialize_tools()

    def _initialize_tools(self) -> Dict[str, ToolType]:
        """
        Load appropriate tools for current platform using parallel initialization.

        Returns:
            Dictionary of initialized tools
        """
        tools: Dict[str, ToolType] = {}

        use_gpu = (
            self.capabilities.gpu_available
            if hasattr(self.capabilities, "gpu_available")
            else None
        )

        def init_accessibility():
            if not self.capabilities.accessibility_api_available:
                return None
            screen_width, screen_height = self.capabilities.screen_resolution
            if self.capabilities.os_type == "macos":
                return MacOSAccessibility(screen_width, screen_height)
            elif self.capabilities.os_type == "windows":
                return WindowsAccessibility(screen_width, screen_height)
            elif self.capabilities.os_type == "linux":
                return LinuxAccessibility(screen_width, screen_height)
            return None

        def init_ocr():
            return OCRTool(use_gpu=use_gpu)

        def init_screenshot():
            return ScreenshotTool()

        def init_input():
            return InputTool(validator=self.coordinate_validator)

        def init_process():
            return ProcessTool()

        def init_file():
            return FileTool(safety_checker=self.safety_checker)

        init_tasks = {
            "accessibility": init_accessibility,
            "ocr": init_ocr,
            "screenshot": init_screenshot,
            "input": init_input,
            "process": init_process,
            "file": init_file,
        }

        if self.capabilities.os_type == "macos":
            try:
                accessibility_tool = init_accessibility()
                if accessibility_tool is not None:
                    tools["accessibility"] = accessibility_tool
            except Exception:
                pass
            init_tasks.pop("accessibility", None)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(func): name for name, func in init_tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    if result is not None:
                        tools[name] = result
                except Exception:
                    pass

        return tools

    def get_gui_tools(self) -> List[ToolType]:
        """
        Get GUI automation tools in priority order.

        Returns:
            List of tools ordered by accuracy (highest first)
        """
        ordered_tools: List[ToolType] = []

        if "accessibility" in self.tools:
            ordered_tools.append(self.tools["accessibility"])

        if "ocr" in self.tools:
            ordered_tools.append(self.tools["ocr"])

        return ordered_tools

    def get_tool(self, tool_name: str) -> Optional[ToolType]:
        """
        Get a specific tool by name.

        Args:
            tool_name: Name of tool to retrieve

        Returns:
            Tool instance or None if not available
        """
        return self.tools.get(tool_name)

    def list_available_tools(self) -> List[str]:
        """
        List names of all available tools.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())

    def get_capabilities_summary(self) -> CapabilitiesSummary:
        """
        Get summary of platform capabilities and available tools.

        Returns:
            CapabilitiesSummary with capability information
        """
        return CapabilitiesSummary(
            os_type=self.capabilities.os_type,
            os_version=self.capabilities.os_version,
            accessibility_api=self.capabilities.accessibility_api_type,
            screen_resolution=self.capabilities.screen_resolution,
            gpu_available=getattr(self.capabilities, "gpu_available", False),
            gpu_type=getattr(self.capabilities, "gpu_type", None),
            available_tools=self.list_available_tools(),
            tier1_available="accessibility" in self.tools,
            tier2_available="ocr" in self.tools,
        )
