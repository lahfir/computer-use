"""
Web automation tool for CrewAI.
Wraps Browser-Use for autonomous web automation.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
import asyncio


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


class WebAutomationTool(BaseTool):
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
        from ..utils.ui import print_info

        print_info(f"🌐 WebAutomationTool executing: {task}")

        browser_agent = self._browser_agent

        if not browser_agent:
            return "ERROR: Browser agent unavailable - browser agent not initialized"

        # Event loop management: handle both async and sync calling contexts
        try:
            running_loop = asyncio.get_running_loop()
            # We're in an async context, but CrewAI called us synchronously
            # This shouldn't happen, but if it does, we need to handle it
            print_info(
                "⚠️ Warning: Running in async context, using nest_asyncio workaround"
            )
            import nest_asyncio

            nest_asyncio.apply()
            result = running_loop.run_until_complete(
                browser_agent.execute_task(task, url)
            )
        except RuntimeError:
            # No running loop - we need to create one or use an existing loop
            # Try to get the event loop that was used to create the LLM clients
            try:
                # Get the existing event loop if available
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    # Loop is closed, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    need_cleanup = True
                else:
                    # Reuse existing loop
                    need_cleanup = False
            except RuntimeError:
                # No event loop at all, create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                need_cleanup = True

            try:
                result = loop.run_until_complete(browser_agent.execute_task(task, url))
            finally:
                # Only clean up if we created a new loop
                if need_cleanup:
                    try:
                        # Cancel all pending tasks
                        pending = asyncio.all_tasks(loop)
                        for pending_task in pending:
                            pending_task.cancel()

                        # Allow tasks to complete cancellation
                        if pending:
                            loop.run_until_complete(
                                asyncio.gather(*pending, return_exceptions=True)
                            )

                        # Shutdown async generators
                        loop.run_until_complete(loop.shutdown_asyncgens())

                        # Shutdown default executor
                        loop.run_until_complete(loop.shutdown_default_executor())
                    except Exception as cleanup_error:
                        print_info(f"⚠️ Event loop cleanup warning: {cleanup_error}")
                    finally:
                        loop.close()

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
                print_info(f"✅ Browser automation completed: {result.action_taken}")
                return output_str
            elif has_data:
                print_info(
                    f"⚠️ Browser automation partially completed: {result.action_taken}"
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
                # Complete failure with no useful data
                error_str = f"❌ FAILED: {result.action_taken}\n⚠️ Error: {result.error}"
                print_info(f"❌ Browser automation failed: {result.error}")
                return error_str
        except Exception as e:
            error_msg = f"❌ ERROR: Browser automation exception - {str(e)}"
            print_info(f"❌ {error_msg}")
            return error_msg
