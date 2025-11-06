"""
Capability-based app finder tool for CrewAI.
Uses LLM intelligence to find best app for capability - NO hardcoding.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import asyncio

from ..schemas.actions import ActionResult


class AppSelection(BaseModel):
    """LLM's app selection decision."""

    selected_app: str = Field(description="Exact app name to use")
    reasoning: str = Field(description="Why this app was selected")
    confidence: float = Field(description="Confidence 0.0-1.0")


class FindAppInput(BaseModel):
    """Input for finding application by capability."""

    capability: str = Field(
        description="Capability needed (e.g., spreadsheet, text_editor, browser)"
    )


class FindApplicationTool(BaseTool):
    """
    Intelligently find best application for capability using LLM.
    NO hardcoded mappings - LLM decides based on running apps.
    """

    name: str = "find_application"
    description: str = """Find best app for capability using AI intelligence.
    
    Examples:
    - capability="spreadsheet" → finds Excel, Numbers, LibreOffice Calc
    - capability="text_editor" → finds TextEdit, Notepad, VS Code
    - capability="browser" → finds Safari, Chrome, Firefox
    - capability="pdf_viewer" → finds Preview, Adobe Acrobat
    
    LLM selects best available app on current platform."""
    args_schema: type[BaseModel] = FindAppInput

    def _run(self, capability: str) -> ActionResult:
        """
        Find app using LLM intelligence:
        1. Get all running/installed apps
        2. Ask LLM which is best for capability
        3. Launch if needed

        Args:
            capability: Capability needed

        Returns:
            ActionResult with app selection
        """
        process_tool = self._tool_registry.get_tool("process")
        platform = self._tool_registry.capabilities.os_type
        llm = self._llm

        if not llm:
            return ActionResult(
                success=False,
                action_taken="LLM unavailable",
                method_used="capability_llm",
                confidence=0.0,
                error="FindApplicationTool requires LLM",
            )

        # Get all running processes
        try:
            all_processes = process_tool.list_running_processes()
            app_names = [p["name"] for p in all_processes]
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="Failed to list apps",
                method_used="capability_llm",
                confidence=0.0,
                error=str(e),
            )

        # Ask LLM to select best app
        structured_llm = llm.with_structured_output(AppSelection)

        prompt = f"""Platform: {platform}
Capability needed: {capability}

Available applications:
{chr(10).join(f"- {app}" for app in sorted(set(app_names)))}

Select the BEST application for this capability.
If no suitable app exists, select "NONE".

Examples:
- capability="spreadsheet" → Microsoft Excel, Numbers, LibreOffice Calc
- capability="text_editor" → TextEdit, Notepad, gedit, vim, VS Code
- capability="pdf_viewer" → Preview, Adobe Acrobat, evince
- capability="browser" → Safari, Chrome, Firefox, Edge
- capability="image_editor" → Preview, Paint, GIMP, Photoshop
- capability="calculator" → Calculator, Spotlight

Select exact app name from the list above.
"""

        try:
            # Run LLM selection
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                selection = loop.run_until_complete(structured_llm.ainvoke(prompt))
            finally:
                loop.close()

            if selection.selected_app == "NONE" or selection.confidence < 0.5:
                return ActionResult(
                    success=False,
                    action_taken="No suitable app found",
                    method_used="capability_llm",
                    confidence=0.0,
                    error=f"No {capability} app available on {platform}",
                    data={"reasoning": selection.reasoning},
                )

            # Check if app is running
            if process_tool.is_process_running(selection.selected_app):
                return ActionResult(
                    success=True,
                    action_taken=f"Found running {selection.selected_app}",
                    method_used="capability_llm",
                    confidence=selection.confidence,
                    data={
                        "app": selection.selected_app,
                        "reasoning": selection.reasoning,
                        "running": True,
                    },
                )

            # Try to launch it
            result = process_tool.open_application(selection.selected_app)
            if result.get("success"):
                return ActionResult(
                    success=True,
                    action_taken=f"Launched {selection.selected_app}",
                    method_used="capability_llm",
                    confidence=selection.confidence,
                    data={
                        "app": selection.selected_app,
                        "reasoning": selection.reasoning,
                        "launched": True,
                    },
                )

            return ActionResult(
                success=False,
                action_taken=f"Failed to launch {selection.selected_app}",
                method_used="capability_llm",
                confidence=0.0,
                error=f"Could not launch {selection.selected_app}",
                data={"reasoning": selection.reasoning},
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="LLM selection failed",
                method_used="capability_llm",
                confidence=0.0,
                error=str(e),
            )

