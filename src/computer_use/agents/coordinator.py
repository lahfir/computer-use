"""
Coordinator agent for task analysis and delegation.
Uses LLM with structured outputs for intelligent task classification.
"""

from ..schemas.task_analysis import TaskAnalysis
from ..prompts.coordinator_prompts import build_coordinator_prompt


class CoordinatorAgent:
    """
    Analyzes user tasks using LLM and delegates to appropriate specialized agents.
    Uses structured outputs to classify tasks and create execution plans.
    """

    def __init__(self, llm_client):
        """
        Initialize coordinator agent.

        Args:
            llm_client: LLM client for intelligent task analysis
        """
        self.llm_client = llm_client

    async def analyze_task(
        self, task: str, conversation_history: list = None
    ) -> TaskAnalysis:
        """
        Analyze user task using LLM and break it down into specific sub-tasks.

        Args:
            task: User's natural language task description
            conversation_history: List of previous messages and responses for context

        Returns:
            TaskAnalysis with classification and specific sub-tasks for each agent
        """
        prompt = build_coordinator_prompt(task, conversation_history)

        structured_llm = self.llm_client.with_structured_output(TaskAnalysis)
        analysis = await structured_llm.ainvoke(prompt)

        return analysis
