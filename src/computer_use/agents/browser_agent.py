"""
Browser agent for web automation using Browser-Use.
"""

from ..schemas.actions import ActionResult


class BrowserAgent:
    """
    Web automation specialist using Browser-Use library.
    Handles all web-based tasks with high accuracy.
    """

    def __init__(self, tool_registry):
        """
        Initialize browser agent.

        Args:
            tool_registry: PlatformToolRegistry instance
        """
        self.tool_registry = tool_registry
        self.browser_tool = tool_registry.get_tool("browser")

    async def execute_task(
        self, task: str, url: str = None, context: dict = None
    ) -> ActionResult:
        """
        Execute web automation task.

        Args:
            task: Natural language task description
            url: Optional starting URL
            context: Context from previous agents

        Returns:
            ActionResult with status and data
        """
        # Add smart handoff guidelines (generic, principle-based)
        handoff_guidelines = """
═══════════════════════════════════════════════════════════
🎯 BROWSER AGENT PRINCIPLES
═══════════════════════════════════════════════════════════

Your role: WEB AUTOMATION SPECIALIST
- Navigate websites, find information, download/extract data
- Work with web pages, forms, downloads, search results
- Other agents handle: desktop apps, file processing, terminal commands

Success = Gathering the requested data, NOT processing it
✅ Downloaded files? → done() (let other agents open/process them)
✅ Extracted to file? → done() (your job complete)
✅ Cannot read file format? → done() if you downloaded it
✅ Task needs desktop app? → done() with data (let GUI agent handle)

Key insight: If you got the data but can't process it further in a browser,
you've succeeded! Call done() and describe what you gathered.

═══════════════════════════════════════════════════════════
"""

        enhanced_task = handoff_guidelines + "\n\n"

        if context and context.get("previous_results"):
            prev_results = context.get("previous_results", [])
            if prev_results:
                context_info = "CONTEXT - Previous work done:\n"
                for res in prev_results:
                    agent_type = res.get("method_used", "unknown")
                    action = res.get("action_taken", "")
                    success = "✅" if res.get("success") else "❌"
                    context_info += f"{success} {agent_type}: {action}\n"
                enhanced_task += context_info + "\n\n"

        enhanced_task += f"YOUR TASK: {task}"

        try:
            result = await self.browser_tool.execute_task(enhanced_task, url)
            return result
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken=task,
                method_used="browser",
                confidence=0.0,
                error=str(e),
            )
