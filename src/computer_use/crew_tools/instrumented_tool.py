"""Instrumented base tool that auto-logs completion to dashboard."""

from crewai.tools import BaseTool

from ..utils.ui import dashboard


class InstrumentedBaseTool(BaseTool):
    """Base tool that automatically logs completion status to dashboard."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_run") and callable(cls._run):
            original_run = cls._run

            def instrumented_run(self, *args, **kwargs):
                tool_name = getattr(self, "name", None)

                agent_switching_tools = {
                    "execute_shell_command",
                    "web_automation",
                    "coding_automation",
                }

                try:
                    current_agent = dashboard.get_current_agent_name()
                    is_manager = current_agent == "Manager"

                    if is_manager and tool_name not in agent_switching_tools:
                        tool_id = None
                    else:
                        tool_id = dashboard.get_pending_tool_id(tool_name)
                        if not tool_id:
                            tool_id = dashboard.log_tool_start(tool_name, kwargs)
                except Exception:
                    tool_id = None

                try:
                    result = original_run(self, *args, **kwargs)

                    success = True
                    action_taken = ""
                    error = None

                    if hasattr(result, "success"):
                        success = result.success
                    if hasattr(result, "action_taken"):
                        action_taken = result.action_taken
                    if hasattr(result, "error"):
                        error = result.error
                    elif isinstance(result, str):
                        if result.startswith("ERROR") or result.startswith("TIMEOUT"):
                            success = False
                            error = result
                        elif result.startswith("SUCCESS"):
                            lines = result.split("\n")
                            output_lines = []
                            for line in lines:
                                if line.startswith("Output"):
                                    output_lines = lines[lines.index(line) + 1 :]
                                    break
                            if output_lines:
                                action_taken = "\n".join(output_lines[:20])
                                if len(output_lines) > 20:
                                    action_taken += (
                                        f"\n... ({len(output_lines) - 20} more lines)"
                                    )

                    if tool_id:
                        dashboard.log_tool_complete(
                            tool_id,
                            success=success,
                            action_taken=action_taken,
                            error=error,
                        )

                    return result
                except Exception as e:
                    if tool_id:
                        dashboard.log_tool_complete(
                            tool_id, success=False, error=str(e)
                        )
                    raise

            cls._run = instrumented_run
