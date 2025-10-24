"""
Intelligent coordinator agent that decides which agent to use next.
"""

from typing import TYPE_CHECKING
from ..schemas.workflow import CoordinatorDecision, WorkflowContext

if TYPE_CHECKING:
    from ..utils.platform_detector import PlatformCapabilities


class CoordinatorAgent:
    """
    Simple coordinator that decides which agent goes next.
    """

    def __init__(self, llm_client, capabilities: "PlatformCapabilities"):
        """
        Initialize coordinator agent.

        Args:
            llm_client: LLM client for intelligent analysis and planning
            capabilities: PlatformCapabilities object (typed, not a dict!)
        """
        self.llm_client = llm_client
        self.capabilities = capabilities

    async def decide_next_action(
        self, original_task: str, context: WorkflowContext
    ) -> CoordinatorDecision:
        """
        Decide next agent and subtask based on current context.

        Args:
            original_task: Original user task
            context: Current workflow context with previous results

        Returns:
            CoordinatorDecision with agent, subtask, and completion status
        """
        context_summary = self._format_context(context)

        prompt = f"""
You are an INTELLIGENT COORDINATOR for a multi-agent system. Your job is to decide which agent should handle the next step.

ORIGINAL TASK: "{original_task}"

WHAT HAPPENED SO FAR:
{context_summary}

AVAILABLE AGENTS & THEIR CAPABILITIES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 BROWSER Agent:
  • Web search, research, data extraction
  • Download files, scrape websites
  • Navigate web pages, fill forms
  • OUTPUTS: Data, files (in temp folders), links
  • WHEN: Need online information, downloads, web research
  
🖥️ GUI Agent:
  • Desktop/native applications (discovers apps automatically)
  • Click, type, interact with UI elements
  • Uses platform Accessibility API (100% accurate)
  • Can open ANY application and interact with it
  • WHEN: Task mentions "app", "application", or needs desktop UI interaction
  
⚙️ SYSTEM Agent:
  • Shell commands (ls, cat, mv, cp, find)
  • File operations, directory management
  • Move/copy files between folders
  • WHEN: Need pure file system operations without UI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

       CRITICAL INTELLIGENCE RULES:
       1. **READ THE CONTEXT**: Previous agents have done work - BUILD ON IT, don't repeat!
       2. **FILE LOCATIONS**: Browser creates files in TEMP folders (/var/folders/...) - shown in context
       3. **COMPLETE TASKS**: Give agents FULL instructions with ALL the data
          - BAD: "Review file and add to app"
          - GOOD: "Open notes app and add this data: [actual 10 gift ideas with links]"
       4. **USE ACTUAL DATA**: Extract and include real content from previous steps
       5. **SMART AGENT CHOICE**: 
          - User says "app/application name" → GUI agent (it will find and open it)
          - Need web info → Browser agent
          - Need file operations only → System agent
       6. **SMART HANDOFFS**: 
          - Last agent FAILED? Check if it was stuck/loop → try a DIFFERENT approach
          - Browser → GUI: Pass the actual data/content, not just file paths
          - GUI stuck/failed? → Try System agent with CLI commands
          - System failed? → Try GUI agent with UI interaction
          - If agent failed with "couldn't find X" → DON'T repeat same approach!
          - HANDOFF = SMART RETRY with a DIFFERENT method, NOT just pass to same agent again!
       7. **FAILURE ANALYSIS**: 
          - If last step shows ❌ Error → understand WHY it failed
          - Don't give the SAME task to the SAME agent that just failed
          - Adapt the approach based on the error message
       8. **COMPLETION**: Only set is_complete=True when ORIGINAL TASK is 100% done

PLATFORM: {self.capabilities.os_type}
ACCESSIBILITY: {"Available" if self.capabilities.accessibility_api_available else "Not available"}

THINK: What's the SMARTEST next step to complete the original task?
"""

        structured_llm = self.llm_client.with_structured_output(CoordinatorDecision)
        decision = await structured_llm.ainvoke(prompt)

        return decision

    def _format_context(self, context: WorkflowContext) -> str:
        """
        Format workflow context for LLM prompt with USEFUL details.

        Args:
            context: Current workflow context

        Returns:
            Formatted context string with file paths, data content, etc.
        """
        if not context.agent_results:
            return "No previous actions yet - this is the first step."

        parts = []
        for i, result in enumerate(context.agent_results, 1):
            status = "✓" if result.success else "✗"

            result_info = (
                f"Step {i}: {status} {result.agent.upper()} - {result.subtask}\n"
            )

            if result.success and result.data:
                data = result.data

                files = data.files
                if files:
                    result_info += f"  📁 Files: {', '.join(files)}\n"

                output = data.output
                if output:
                    result_info += f"  📄 Output: {output}\n"

                final_output = data.final_output
                if final_output:
                    result_info += f"  ✅ Result: {final_output}\n"

                steps = data.steps
                if steps:
                    result_info += f"  📊 Steps: {steps}\n"

            elif not result.success:
                result_info += f"  ❌ Error: {result.error}\n"
            parts.append(result_info)

        return "\n".join(parts)
