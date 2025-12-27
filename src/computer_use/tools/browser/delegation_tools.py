"""Delegation tools for Browser-Use.

These tools allow the Browser-Use autonomous agent to temporarily delegate
OS-native dialog handling (permission prompts, desktop app dialogs) to the
existing CrewAI GUI specialist agent, then resume browser control.

NOTE: For web file uploads, use browser-use's native upload_file action.
GUI delegation is only needed for truly OS-native dialogs that cannot be
controlled programmatically via the browser.
"""

from typing import Optional

from browser_use import ActionResult, Tools


def load_delegation_tools(gui_delegate=None) -> Optional[Tools]:
    """Load delegation tools if a GUI delegate is provided."""
    if gui_delegate is None:
        return None

    tools = Tools()

    @tools.action(
        description=(
            "Delegate OS-native dialog handling to GUI agent. "
            "Use for OS permission prompts or desktop app dialogs. "
            "Do NOT use for web file uploads (use upload_file) or CAPTCHA/QR/2FA (use request_human_help)."
        )
    )
    def delegate_to_gui(task: str) -> ActionResult:
        """Delegate an OS dialog task to the GUI specialist and return control."""
        result = gui_delegate.run_os_dialog_task(task)

        if result.success:
            return ActionResult(
                extracted_content=(
                    "GUI delegation completed. Resume the browser task and verify the page state.\n\n"
                    f"GUI RESULT:\n{result.output}"
                ),
                long_term_memory=f"Delegated OS dialog task: {task}",
            )

        return ActionResult(
            extracted_content=(
                "GUI delegation did not complete successfully. "
                "Adapt your approach, retry with clearer instructions, or use request_human_help if truly human-only.\n\n"
                f"GUI RESULT:\n{result.output}"
            ),
            error="GUI delegation failed",
        )

    return tools
