"""
Web automation tool for CrewAI.
Wraps Browser-Use for autonomous web automation.
"""

from pydantic import BaseModel, Field
from typing import Optional
import asyncio

try:
    import nest_asyncio

    nest_asyncio.apply()
    _NEST_ASYNCIO_APPLIED = True
except ImportError:
    _NEST_ASYNCIO_APPLIED = False

from .instrumented_tool import InstrumentedBaseTool


class WebAutomationInput(BaseModel):
    """Input for web automation.

    CRITICAL: 'task' must be a PLAIN STRING, not a dict or object!

    CORRECT:   {"task": "Search for Nvidia stock"}
    WRONG:     {"task": {"description": "...", "type": "str"}}
    """

    task: str = Field(
        ...,
        description="PLAIN STRING (not dict!) describing web task. Examples: 'Search Google for Nvidia stock price' or 'Go to yahoo.com and extract data'",
        json_schema_extra={
            "example": "Navigate to Google Finance and get NVDA stock price"
        },
    )
    url: Optional[str] = Field(
        default=None,
        description="Optional starting URL as PLAIN STRING. Example: 'https://finance.yahoo.com'",
        json_schema_extra={"example": "https://google.com"},
    )


class WebAutomationTool(InstrumentedBaseTool):
    """
    Autonomous web automation via Browser-Use.
    Handles navigation, data extraction, form filling, downloads.
    Phone verification handled internally via Twilio.
    """

    name: str = "web_automation"
    description: str = """Autonomous web automation using Browser-Use.
    
    Input: Provide 'task' as a PLAIN STRING (not a dict).
    Examples: 
    - task="Search for Nvidia stock price on Google Finance"
    - task="Download the latest report from example.com"
    
    Capabilities:
    - Navigate websites, click, type, fill forms
    - Extract data from pages
    - Download files (returns file path for other agents)
    - Phone verification (internal)
    
    Output: Returns extracted data and file paths that other agents can use."""
    args_schema: type[BaseModel] = WebAutomationInput

    def _run(self, task: str, url: Optional[str] = None) -> str:
        """
        Execute web automation task.
        Calls browser_agent.execute_task directly.

        Event Loop Management:
        - CrewAI calls this synchronously from a thread pool executor
        - The browser_use agent needs an event loop for async operations
        - The LLM client was initialized in the main event loop
        - We must use the SAME event loop to avoid "Event loop is closed" errors
        - Strategy: Reuse existing loop if available, only create new if necessary

        Args:
            task: Web task description
            url: Optional starting URL

        Returns:
            String result for CrewAI
        """
        from ..utils.ui import dashboard, ActionType

        if dashboard.get_current_agent_name() == "Manager":
            dashboard.set_agent("Browser Agent")
            dashboard.set_thinking(f"Web automation: {task[:80]}...")

        dashboard.mark_external_tool_executed()

        dashboard.add_log_entry(
            ActionType.NAVIGATE, f"WebAutomationTool executing: {task}"
        )

        browser_agent = self._browser_agent

        if not browser_agent:
            return "ERROR: Browser agent unavailable - browser agent not initialized"

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                if _NEST_ASYNCIO_APPLIED:
                    result = loop.run_until_complete(
                        browser_agent.execute_task(task, url)
                    )
                else:
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run, browser_agent.execute_task(task, url)
                        )
                        result = future.result()
            else:
                result = asyncio.run(browser_agent.execute_task(task, url))
        except Exception as exec_error:
            dashboard.add_log_entry(
                ActionType.ERROR,
                f"Browser execution error: {exec_error}",
                status="error",
            )
            raise

        # Process result
        try:
            has_data = False
            if result.data:
                has_data = any(
                    key in result.data
                    for key in ["output", "text", "file_path", "download_path"]
                )

            if result.success:
                # Build structured output for CrewAI context passing
                output_parts = [f"✅ SUCCESS: {result.action_taken}"]

                # Add extracted data
                if result.data:
                    if "output" in result.data:
                        output_parts.append(
                            f"\n📊 EXTRACTED DATA:\n{result.data['output']}"
                        )
                    if "text" in result.data:
                        output_parts.append(f"\n📝 TEXT:\n{result.data['text']}")
                    if "file_path" in result.data:
                        output_parts.append(
                            f"\n📁 DOWNLOADED FILE: {result.data['file_path']}"
                        )
                    if "download_path" in result.data:
                        output_parts.append(
                            f"\n📁 DOWNLOADED FILE: {result.data['download_path']}"
                        )

                output_str = "".join(output_parts)
                dashboard.add_log_entry(
                    ActionType.COMPLETE,
                    f"Browser automation completed: {result.action_taken}",
                    status="complete",
                )
                return output_str
            elif has_data:
                dashboard.add_log_entry(
                    ActionType.NAVIGATE,
                    f"Browser automation partial: {result.action_taken}",
                )
                output_parts = [
                    f"⚠️ PARTIAL SUCCESS: {result.action_taken}",
                    f"\n⚠️ Note: Task completed partially. {result.error or 'Some operations failed.'}",
                ]

                if "output" in result.data:
                    output_parts.append(
                        f"\n📊 EXTRACTED DATA:\n{result.data['output']}"
                    )
                if "text" in result.data:
                    output_parts.append(f"\n📝 TEXT:\n{result.data['text']}")
                if "file_path" in result.data:
                    output_parts.append(
                        f"\n📁 DOWNLOADED FILE: {result.data['file_path']}"
                    )
                if "download_path" in result.data:
                    output_parts.append(
                        f"\n📁 DOWNLOADED FILE: {result.data['download_path']}"
                    )

                return "".join(output_parts)
            else:
                error_str = f"❌ FAILED: {result.action_taken}\n⚠️ Error: {result.error}"
                dashboard.add_log_entry(
                    ActionType.ERROR, f"Browser failed: {result.error}", status="error"
                )
                raise Exception(error_str)
        except Exception as e:
            error_msg = f"Browser automation exception - {str(e)}"
            dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
            raise Exception(f"❌ ERROR: {error_msg}")
