"""
Coding automation tool for CrewAI.
Wraps CodingAgent (Cline CLI) for autonomous code automation.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import asyncio


class CodingAutomationInput(BaseModel):
    """Input schema for coding automation tool."""

    task: str = Field(
        ...,
        description="The coding task to execute (plain text string)",
    )


class CodingAgentTool(BaseTool):
    """
    Autonomous coding automation via Cline CLI.
    Handles code writing, refactoring, bug fixes, tests, and features.
    """

    name: str = "coding_automation"
    description: str = (
        "Execute coding tasks using Cline AI. "
        "Pass a single 'task' string describing what code to write, fix, or modify. "
        "Example: coding_automation(task='Create a Python snake game with pygame')"
    )
    args_schema: type[BaseModel] = CodingAutomationInput

    def _run(self, task: str) -> str:
        """
        Execute coding task via CodingAgent.

        Args:
            task: Coding task description

        Returns:
            String result for CrewAI
        """
        from ..utils.ui import dashboard, ActionType

        dashboard.add_log_entry(ActionType.EXECUTE, f"CodingAgentTool: {task}")

        coding_agent = self._coding_agent

        if not coding_agent:
            return "ERROR: Coding agent unavailable - not initialized"

        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                need_cleanup = True
            else:
                need_cleanup = False
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            need_cleanup = True

        try:
            result = loop.run_until_complete(coding_agent.execute_task(task))
        finally:
            if need_cleanup:
                try:
                    pending = asyncio.all_tasks(loop)
                    for pending_task in pending:
                        pending_task.cancel()
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                finally:
                    loop.close()

        try:
            if result.success:
                output_parts = [f"✅ SUCCESS: {result.action_taken}"]

                if result.data:
                    if "output" in result.data:
                        output_parts.append(f"\n📝 OUTPUT:\n{result.data['output']}")

                output_str = "".join(output_parts)
                dashboard.add_log_entry(
                    ActionType.COMPLETE,
                    f"Coding completed: {result.action_taken}",
                    status="complete",
                )
                return output_str
            else:
                error_str = f"❌ FAILED: {result.action_taken}\n⚠️ Error: {result.error}"
                dashboard.add_log_entry(
                    ActionType.ERROR, f"Coding failed: {result.error}", status="error"
                )
                raise Exception(error_str)
        except Exception as e:
            error_msg = f"Coding automation exception: {str(e)}"
            dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
            raise Exception(f"❌ ERROR: {error_msg}")
