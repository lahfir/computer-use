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
                tool_id = dashboard.get_pending_tool_id(tool_name)

                try:
                    result = original_run(self, *args, **kwargs)

                    if tool_id:
                        success = True
                        action_taken = ""
                        error = None

                        if hasattr(result, "success"):
                            success = result.success
                        if hasattr(result, "action_taken"):
                            action_taken = result.action_taken
                        if hasattr(result, "error"):
                            error = result.error
                        elif isinstance(result, str) and result.startswith("ERROR"):
                            success = False
                            error = result

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
