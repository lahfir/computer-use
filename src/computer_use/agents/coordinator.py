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

⚠️ FIRST: CHECK IF TASK IS ALREADY COMPLETE!
If previous steps accomplished what user asked for → SET is_complete=True immediately!
DON'T create new steps just because you can. Check if user's goal is achieved!

🚨 CRITICAL RULES - READ BEFORE EVERY DECISION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **GIVE COMPLETE TASKS - DON'T MICRO-MANAGE!**
   ❌ BAD: "Open Calculator" → then another step "Type 291+1298"
   ✅ GOOD: "Open Calculator, type 291+1298, read the result"
   
   ❌ BAD: "Search for X" → then "Extract data" → then "Save to file"
   ✅ GOOD: "Search for X, extract data, save to file at ~/Downloads/data.txt"
   
   WHY: Agents are SMART! They can do multi-step tasks autonomously!
   Each agent runs in a loop until their task is done. Let them work!

2. **CHOOSE THE RIGHT AGENT FOR THE ENTIRE WORKFLOW**
   - Task mentions "Calculator app" → GUI agent (it will open + interact)
   - Task mentions "research online" → Browser agent (it will search + extract + save)
   - Task mentions "move files" → System agent (it will find + move)
   
   DON'T break into micro-steps across agents! Pick ONE agent for the whole task!

3. **IS THE TASK ALREADY COMPLETE?**
   - If agents accomplished what user asked → SET is_complete=True!
   - DON'T create "verification" or "check" steps - those are micro-managing!

4. **AM I STUCK IN A LOOP?**
   - If last 2 steps did similar things → SET is_complete=True!
   - Loop detection will catch this, but YOU should notice first!

5. **HONOR HANDOFF REQUESTS**
   - Agent explicitly requested handoff to X → CHOOSE agent X!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

       HOW TO CREATE SUBTASKS:
       
       ✅ GOOD EXAMPLES:
       - User: "Open Calculator and calculate 291+1298"
         → Subtask: "Open Calculator app, type 291+1298, note the result"
         → Agent: GUI (ONE agent does it all!)
         
       - User: "Research Nvidia stock and create table in Numbers"
         → Step 1: "Research Nvidia stock price, extract data to CSV" (Browser)
         → Step 2: "Open Numbers app, create table with data: [actual data here]" (GUI)
         
       - User: "Find all PDFs in Downloads and move to Documents"
         → Subtask: "Find all PDF files in ~/Downloads and move them to ~/Documents/PDFs"
         → Agent: System (ONE agent does it all!)
       
       ❌ BAD EXAMPLES (DON'T DO THIS):
       - User: "Open Calculator and calculate 291+1298"
         → ❌ Step 1: "Open Calculator" (too micro!)
         → ❌ Step 2: "Type 291+1298" (micro-managing!)
         → ❌ Step 3: "Read result" (unnecessary split!)
         
       - User: "Research topic"
         → ❌ Step 1: "Search for topic" 
         → ❌ Step 2: "Extract data" (let Browser agent do both!)
       
       KEY PRINCIPLE: Trust agents to handle multi-step workflows autonomously!

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

                def get_field(obj, field_name):
                    if isinstance(obj, dict):
                        return obj.get(field_name)
                    return getattr(obj, field_name, None)

                files = get_field(data, "files")
                if files:
                    result_info += f"  📁 Files: {', '.join(files)}\n"

                output = get_field(data, "output")
                if output:
                    if isinstance(output, str):
                        preview = output[:500] + "..." if len(output) > 500 else output
                        result_info += f"  📄 Output: {preview}\n"

                final_output = get_field(data, "final_output")
                if final_output:
                    result_info += f"  ✅ Result: {final_output}\n"

                steps = get_field(data, "steps")
                if steps:
                    result_info += f"  📊 Steps: {steps}\n"

                text = get_field(data, "text")
                if text and isinstance(text, str):
                    preview = text[:300] + "..." if len(text) > 300 else text
                    result_info += f"  📝 Text: {preview}\n"

            elif not result.success:
                result_info += f"  ❌ Error: {result.error}\n"

                if result.handoff_requested and result.suggested_agent:
                    result_info += (
                        f"  🔀 HANDOFF REQUESTED → {result.suggested_agent.upper()}\n"
                    )
                    result_info += (
                        f"  📝 Reason: {result.handoff_reason or 'Not specified'}\n"
                    )

            parts.append(result_info)

        return "\n".join(parts)
