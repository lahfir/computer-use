"""
Coordinator agent for task analysis and delegation.
Uses LLM with structured outputs for intelligent task classification.
"""

from ..schemas.task_analysis import TaskAnalysis


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

    async def analyze_task(self, task: str) -> TaskAnalysis:
        """
        Analyze user task using LLM - ONLY classify and delegate, nothing more.

        Args:
            task: User's natural language task description

        Returns:
            TaskAnalysis with classification for delegation
        """
        prompt = f"""
You are a task router. Your ONLY job is to analyze the task and decide which agents to delegate to.

Task: "{task}"

Classify which agents are needed:

**Task Type** (choose ONE):
- "browser": Anything involving web/downloads/searches
- "gui": Desktop apps (open Calculator, click buttons, etc.)
- "system": Files/folders/terminal commands
- "hybrid": Multiple types needed

**Agent Requirements** (true/false for each):
- requires_browser: Does this need web automation?
- requires_gui: Does this need desktop app interaction?
- requires_system: Does this need file/folder/terminal operations?

**Reasoning**: One sentence why you classified it this way.

Examples:
- "Download image of Ronaldo" → browser=true, gui=false, system=false
- "Open Calculator" → browser=false, gui=true, system=false
- "Create folder in Downloads" → browser=false, gui=false, system=true
- "Download and save to folder" → hybrid, browser=true, system=true

Return ONLY the classification. The specialized agents will handle execution.
"""

        # Use LLM with structured output
        structured_llm = self.llm_client.with_structured_output(TaskAnalysis)
        analysis = await structured_llm.ainvoke(prompt)

        return analysis
