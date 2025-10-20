"""
Browser automation tool using Browser-Use library.
"""

from typing import Optional, Dict, Any


class BrowserTool:
    """
    Browser-Use integration for web automation.
    Browser-Use Agent handles all browser interactions internally.
    """

    def __init__(self, llm_client=None):
        """
        Initialize browser tool with Browser-Use.

        Args:
            llm_client: LLM client for browser agent (from LLMConfig)
        """
        self.browser_session = None
        self.llm_client = llm_client
        self.available = self._initialize_browser()

    def _initialize_browser(self) -> bool:
        """
        Initialize Browser-Use library.

        Returns:
            True if initialization successful
        """
        try:
            from browser_use import BrowserSession

            self.BrowserSession = BrowserSession
            return True
        except ImportError:
            print("Browser-Use not available. Install with: pip install browser-use")
            return False

    async def execute_task(
        self, task: str, url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a web automation task using Browser-Use Agent.

        Browser-Use handles everything: navigation, clicking, typing, data extraction.
        We just pass the task and it figures out all the actions needed.

        Args:
            task: Natural language description of task (e.g., "Download HD image of Ronaldo")
            url: Optional starting URL

        Returns:
            Result dictionary with status and data
        """
        if not self.available:
            return {
                "success": False,
                "error": "Browser-Use not initialized. Install with: pip install browser-use",
            }

        if not self.llm_client:
            return {
                "success": False,
                "error": "No LLM client provided for Browser-Use Agent",
            }

        try:
            from browser_use import Agent, BrowserSession, BrowserProfile

            full_task = f"Navigate to {url} and {task}" if url else task

            browser_session = BrowserSession(browser_profile=BrowserProfile())

            agent = Agent(
                task=full_task, llm=self.llm_client, browser_session=browser_session
            )

            result = await agent.run()

            await browser_session.kill()

            has_errors = False
            error_msgs = []
            final_output = None
            agent_called_done = False
            task_completed_successfully = False
            files_to_display = []

            if result and hasattr(result, "errors") and result.errors():
                has_errors = True
                error_msgs = [str(e) for e in result.errors() if e]

            if result and hasattr(result, "history"):
                for item in result.history:
                    if hasattr(item, "result") and item.result:
                        for r in item.result:
                            if hasattr(r, "error") and r.error:
                                has_errors = True
                                error_msgs.append(r.error)

                    if hasattr(item, "model_output") and item.model_output:
                        if (
                            hasattr(item.model_output, "done")
                            and item.model_output.done
                        ):
                            agent_called_done = True
                            if hasattr(item.model_output.done, "text"):
                                final_output = item.model_output.done.text
                            if hasattr(item.model_output.done, "success"):
                                task_completed_successfully = (
                                    item.model_output.done.success
                                )
                            if hasattr(item.model_output.done, "files_to_display"):
                                files_to_display = (
                                    item.model_output.done.files_to_display
                                )

            if agent_called_done:
                return {
                    "success": task_completed_successfully,
                    "message": f"Browser task completed: {task}",
                    "data": {
                        "result": str(result),
                        "output": final_output or "Task completed",
                        "task_complete": agent_called_done,
                        "files": files_to_display,
                    },
                }
            elif has_errors and error_msgs:
                return {
                    "success": False,
                    "error": "; ".join(error_msgs),
                    "data": {"result": str(result), "output": final_output},
                }

            return {
                "success": True,
                "message": f"Browser task completed: {task}",
                "data": {
                    "result": str(result),
                    "output": final_output or "Task completed successfully",
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close(self):
        """
        Close browser instance if needed.
        Browser-Use handles cleanup automatically.
        """
        if self.browser_session:
            try:
                await self.browser_session.kill()
            except Exception:
                pass
