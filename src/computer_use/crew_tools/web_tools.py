"""
Web automation tool for CrewAI.
Wraps Browser-Use for autonomous web automation.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
import asyncio


class WebAutomationInput(BaseModel):
    """Input for web automation."""

    task: str = Field(description="Web task to complete")
    url: Optional[str] = Field(default=None, description="Starting URL (optional)")


class WebAutomationTool(BaseTool):
    """
    Autonomous web automation via Browser-Use.
    Handles navigation, data extraction, form filling, downloads.
    Phone verification handled internally via Twilio.
    """

    name: str = "web_automation"
    description: str = """Autonomous web automation using Browser-Use.
    
    Capabilities:
    - Navigate websites, click, type, fill forms
    - Extract data from pages
    - Download files
    - Phone verification (internal)
    
    Runs autonomously until task complete."""
    args_schema: type[BaseModel] = WebAutomationInput

    def _run(self, task: str, url: Optional[str] = None) -> str:
        """
        Execute web automation task.
        Wraps browser_tool.execute_task.

        Args:
            task: Web task description
            url: Optional starting URL

        Returns:
            String result for CrewAI
        """
        from ..utils.ui import print_info

        print_info(f"🌐 WebAutomationTool executing: {task}")

        browser_tool = self._tool_registry.get_tool("browser")

        if not browser_tool:
            return "ERROR: Browser tool unavailable - browser tool not initialized"

        # Execute in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(browser_tool.execute_task(task, url))

            if result.success:
                output_str = f"SUCCESS: {result.action_taken}\n"
                if result.data and "output" in result.data:
                    output_str += f"Data: {result.data['output']}\n"
                print_info(f"✅ Browser automation completed: {result.action_taken}")
                return output_str
            else:
                error_str = f"FAILED: {result.action_taken}\nError: {result.error}"
                print_info(f"❌ Browser automation failed: {result.error}")
                return error_str

        except Exception as e:
            error_msg = f"ERROR: Browser automation exception - {str(e)}"
            print_info(f"❌ {error_msg}")
            return error_msg
        finally:
            loop.close()
