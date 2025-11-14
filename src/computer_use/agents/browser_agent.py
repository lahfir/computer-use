"""
Browser agent for web automation using Browser-Use.
Contains Browser-Use Agent creation and execution logic.
"""

from pathlib import Path
from typing import Optional
import tempfile
import glob

from ..schemas.actions import ActionResult
from ..schemas.browser_output import BrowserOutput, FileDetail
from ..prompts.browser_prompts import build_full_context
from ..tools.browser import load_browser_tools


class BrowserAgent:
    """
    Web automation specialist using Browser-Use library.
    Handles all web-based tasks with Browser-Use autonomous agent.
    """

    def __init__(self, llm_client):
        """
        Initialize browser agent with Browser-Use.

        Args:
            llm_client: LLM client for Browser-Use Agent
        """
        self.llm_client = llm_client
        self.browser_tools = load_browser_tools()
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
        self, task: str, url: Optional[str] = None, context: dict = None
    ) -> ActionResult:
        """
        Execute web automation task using Browser-Use Agent.

        Browser-Use handles everything: navigation, clicking, typing, data extraction.
        We pass the task and it figures out all the actions needed.

        Args:
            task: Natural language task description
            url: Optional starting URL (unused - Browser-Use navigates automatically)
            context: Optional context from previous agents (unused for now)

        Returns:
            ActionResult with browser output and file tracking
        """
        if not self.available:
            return ActionResult(
                success=False,
                action_taken="Browser initialization failed",
                method_used="browser",
                confidence=0.0,
                error="Browser-Use not initialized. Install with: pip install browser-use",
            )

        if not self.llm_client:
            return ActionResult(
                success=False,
                action_taken="No LLM client provided",
                method_used="browser",
                confidence=0.0,
                error="No LLM client provided for Browser-Use Agent",
            )

        try:
            from browser_use import Agent, BrowserSession, BrowserProfile
            from browser_use.agent.views import AgentHistoryList

            has_tools = self.browser_tools is not None
            tool_context = build_full_context(has_twilio=has_tools)
            full_task = tool_context + "\n\n" + task

            temp_dir = Path(tempfile.mkdtemp(prefix="browser_agent_"))

            browser_session = BrowserSession(browser_profile=BrowserProfile())

            agent = Agent(
                task=full_task,
                llm=self.llm_client,
                browser_session=browser_session,
                tools=self.browser_tools,
                max_failures=5,
            )

            result: AgentHistoryList = await agent.run(max_steps=30)

            try:
                await browser_session.kill()
            except Exception:
                pass

            downloaded_files = []
            file_details = []

            download_dirs = glob.glob(
                str(Path(tempfile.gettempdir()) / "browser-use-downloads-*")
            )
            for download_dir in download_dirs:
                for file_path in Path(download_dir).rglob("*"):
                    if file_path.is_file():
                        downloaded_files.append(str(file_path.absolute()))
                        file_details.append(
                            FileDetail(
                                path=str(file_path.absolute()),
                                name=file_path.name,
                                size=file_path.stat().st_size,
                            )
                        )

            browser_output = BrowserOutput(
                text=result.final_result() or "Task completed",
                files=downloaded_files,
                file_details=file_details,
                work_directory=str(temp_dir),
            )

            is_successful = result.is_successful()
            has_errors = bool(result.errors())

            if result.is_done():
                success = is_successful if is_successful is not None else not has_errors
                error_msg = (
                    "; ".join(str(e) for e in result.errors() if e)
                    if has_errors
                    else None
                )

                return ActionResult(
                    success=success,
                    action_taken=f"Browser task: {task}",
                    method_used="browser",
                    confidence=1.0 if success else 0.0,
                    error=error_msg,
                    data=browser_output.model_dump(),
                )

            return ActionResult(
                success=not has_errors,
                action_taken=f"Browser task: {task}",
                method_used="browser",
                confidence=0.5,
                error=(
                    "Agent reached max steps without completing" if has_errors else None
                ),
                data=browser_output.model_dump(),
            )

        except Exception as e:
            error_msg = str(e)
            print(f"[BrowserAgent] Exception during browser task: {error_msg}")

            if "Event loop is closed" in error_msg:
                error_msg = (
                    "Browser session event loop error (browser-use library issue with async cleanup). "
                    f"Original error: {error_msg}"
                )

            return ActionResult(
                success=False,
                action_taken=f"Browser task exception: {task}",
                method_used="browser",
                confidence=0.0,
                error=error_msg,
            )
