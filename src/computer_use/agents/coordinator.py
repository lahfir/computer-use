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
Coordinate agents to complete: "{original_task}"

CONTEXT: {context_summary}

AGENTS:
- browser: Web tasks
- gui: Desktop apps
- system: Files/commands

RULES:
• Give agents COMPLETE tasks, not tiny steps (e.g., "Open Calculator and calculate X+Y", not just "Open Calculator")
• If task is done, set is_complete=True
• Otherwise, decide which agent + what full subtask

What's next?
"""

        structured_llm = self.llm_client.with_structured_output(CoordinatorDecision)
        decision = await structured_llm.ainvoke(prompt)

        return decision

    def _format_context(self, context: WorkflowContext) -> str:
        """
        Format workflow context for LLM prompt.

        Args:
            context: Current workflow context

        Returns:
            Formatted context string
        """
        if not context.agent_results:
            return "No previous actions yet - this is the first step."

        parts = []
        for i, result in enumerate(context.agent_results, 1):
            status = "✓" if result.success else "✗"
            parts.append(
                f"Step {i}: {status} {result.agent} - {result.subtask}\n"
                f"  Result: {result.data if result.success else result.error}"
            )

        return "\n".join(parts)
