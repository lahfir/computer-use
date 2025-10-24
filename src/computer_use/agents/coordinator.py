"""
Intelligent coordinator agent for task analysis, workflow planning,
and CrewAI Task creation with rich context.
"""

from typing import List, TYPE_CHECKING
from crewai import Task
from ..schemas.workflow import TaskUnderstanding, WorkflowPlan, WorkflowStep

if TYPE_CHECKING:
    from ..utils.platform_detector import PlatformCapabilities


class CoordinatorAgent:
    """
    Transforms user requests into intelligent CrewAI Task objects.
    Creates detailed, context-aware tasks with proper agent routing.
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

    async def create_intelligent_tasks(
        self, user_request: str, available_agents: dict
    ) -> List[Task]:
        """
        Analyze user request and create intelligent CrewAI Task objects.

        This is the core intelligence - transforms vague requests into
        detailed, context-aware tasks that agents can execute.

        Args:
            user_request: User's natural language request
            available_agents: Dictionary of agent_type -> Agent instance

        Returns:
            List of CrewAI Task objects with proper context and descriptions
        """
        understanding = await self._understand_intent(user_request)

        workflow = await self._plan_workflow(understanding)

        tasks = []
        for step in workflow.steps:
            agent = self._select_agent(step.agent_type, available_agents)

            description = await self._craft_detailed_description(
                step, understanding, tasks
            )

            task = Task(
                description=description,
                agent=agent,
                expected_output=step.expected_output,
                context=tasks[-1:] if tasks else [],
            )
            tasks.append(task)

        return tasks

    async def _understand_intent(self, user_request: str) -> TaskUnderstanding:
        """
        Deep understanding of user intent using LLM.

        Analyzes the request to determine what the user truly wants,
        not just surface-level classification.

        Args:
            user_request: User's request

        Returns:
            TaskUnderstanding with intent, steps, criteria, etc.
        """
        prompt = f"""
Analyze this user request deeply to understand their true intent:

"{user_request}"

Provide a comprehensive analysis:

1. PRIMARY INTENT: What does the user ultimately want to achieve? (Be specific about the end goal)

2. REQUIRED STEPS: Break down into logical steps (3-5 steps typically)
   - Think about the natural workflow
   - Consider dependencies between steps
   - Don't over-complicate simple tasks

3. SUCCESS CRITERIA: How will we know the task is complete?
   - What should exist when done?
   - What state should the system be in?

4. POTENTIAL CHALLENGES: What might block progress?
   - Missing permissions?
   - Apps not installed?
   - Network issues?
   - Data not available?

5. RESOURCE REQUIREMENTS: What resources are needed?
   - Websites/URLs to visit
   - Applications to open
   - Files to create/modify
   - Data to extract

Think step-by-step about the complete workflow from start to finish.
"""

        structured_llm = self.llm_client.with_structured_output(TaskUnderstanding)
        understanding = await structured_llm.ainvoke(prompt)
        return understanding

    async def _plan_workflow(self, understanding: TaskUnderstanding) -> WorkflowPlan:
        """
        Create step-by-step workflow execution plan.

        Decomposes the task into agent-specific steps that build on each other.

        Args:
            understanding: Deep understanding of user intent

        Returns:
            WorkflowPlan with ordered steps
        """
        prompt = f"""
Create a detailed execution plan to achieve this goal:

GOAL: {understanding.intent}

REQUIRED STEPS: {understanding.required_steps}

For each step in your plan, specify:

1. AGENT TYPE: Which agent should handle it?
   - "browser": Web research, downloads, online data extraction
   - "gui": Desktop app interaction, file opening, UI manipulation
   - "system": File operations, terminal commands, organization

2. ROLE: What should this specific agent accomplish? (One clear objective)

3. INSTRUCTIONS: Detailed what to do (will be expanded later)

4. EXPECTED OUTPUT: What should this step produce?
   - File paths if creating files
   - Confirmation messages if verifying
   - Data summaries if extracting

5. DEPENDS ON: Which previous steps does this depend on?

CRITICAL RULES:
- Each step should build on previous work - no duplication!
- Browser agent saves to permanent locations (~/Documents/AgentWorkspace/[task-name]/)
- System agent should use files created by Browser agent, not recreate them
- If task is simple (1-2 steps), don't over-complicate it
- Steps should be in logical order

Example for "Research X and create document":
Step 1 (browser): Research X, save to ~/Documents/AgentWorkspace/research-x/data.md
Step 2 (gui): Open Notes app with data.md, format as document

Now create the execution plan:
"""

        structured_llm = self.llm_client.with_structured_output(WorkflowPlan)
        plan = await structured_llm.ainvoke(prompt)
        return plan

    async def _craft_detailed_description(
        self,
        step: WorkflowStep,
        understanding: TaskUnderstanding,
        previous_tasks: List[Task],
    ) -> str:
        """
        Craft detailed, context-aware task description for specific agent.

        This is KEY intelligence - each agent gets full context about:
        - Overall mission goal
        - What previous agents did
        - What resources are available
        - Exactly what to do next

        Args:
            step: Current workflow step
            understanding: Overall task understanding
            previous_tasks: Tasks completed/planned before this one

        Returns:
            Detailed task description string
        """
        previous_context = self._format_previous_context(previous_tasks)

        # Use actual Pydantic model attributes, not dict!
        os_type = self.capabilities.os_type
        tools = self.capabilities.supported_tools
        accessibility = f"{self.capabilities.accessibility_api_type} (100% accurate)" if self.capabilities.accessibility_api_available else "Not available"
        
        prompt = f"""
You are crafting detailed instructions for a {step.agent_type} agent.

═══════════════════════════════════════════════════════════
SYSTEM ENVIRONMENT
═══════════════════════════════════════════════════════════
OPERATING SYSTEM: {os_type}
ACCESSIBILITY API: {accessibility}
AVAILABLE TOOLS: {", ".join(tools)}

CRITICAL: This is {os_type}, NOT Windows!
- Use macOS commands (e.g., 'open Calculator' NOT 'C:\\Windows\\calc.exe')
- Use bash commands, NOT PowerShell
- Use macOS accessibility API when available
- Use '~/' for home directory, not Windows paths

═══════════════════════════════════════════════════════════
MISSION CONTEXT
═══════════════════════════════════════════════════════════
USER'S OVERALL GOAL: {understanding.intent}

SUCCESS CRITERIA: {understanding.success_criteria}

PREVIOUS WORK COMPLETED:
{previous_context}

THIS AGENT'S SPECIFIC ROLE: {step.role}

BASIC INSTRUCTIONS: {step.instructions}

═══════════════════════════════════════════════════════════
YOUR TASK: CREATE DETAILED AGENT INSTRUCTIONS
═══════════════════════════════════════════════════════════

Create a comprehensive task description that includes:

1. MISSION STATEMENT: Explain overall goal and this agent's part

2. CONTEXT: What previous agents did (if any)
   - Reference specific file paths
   - Mention available resources
   - Note what's already complete

3. DETAILED INSTRUCTIONS: Step-by-step what to do
   - Be specific about file locations
   - Specify output format
   - Include success checks

4. OUTPUT REQUIREMENTS: What to produce
   - File paths with full locations
   - Data format specifications
   - Confirmation messages

5. CRITICAL REMINDERS:
   - "Use available resources - don't recreate existing work!"
   - "Save to permanent locations, not temp directories"
   - "Provide clear output for next agents"

Format the description as clear, actionable instructions.
Make it detailed enough that the agent knows EXACTLY what to do.
"""

        response = await self.llm_client.ainvoke(prompt)

        if hasattr(response, "content"):
            return response.content
        return str(response)

    def _format_previous_context(self, previous_tasks: List[Task]) -> str:
        """
        Format previous task context for display.

        Args:
            previous_tasks: List of previous tasks

        Returns:
            Formatted string describing previous work
        """
        if not previous_tasks:
            return "No previous work - this is the first step."

        context_parts = []
        for i, task in enumerate(previous_tasks, 1):
            agent_role = getattr(task.agent, "role", "Unknown agent")
            expected = task.expected_output
            context_parts.append(
                f"Step {i} ({agent_role}): Expected to produce {expected}"
            )

        return "\n".join(context_parts)

    def _select_agent(self, agent_type: str, available_agents: dict):
        """
        Select appropriate agent based on type.

        Args:
            agent_type: Type of agent needed ('browser', 'gui', 'system')
            available_agents: Dictionary of available agents

        Returns:
            Selected agent instance
        """
        agent_map = {
            "browser": "browser",
            "gui": "gui",
            "system": "system",
        }

        agent_key = agent_map.get(agent_type.lower(), "system")
        return available_agents.get(agent_key)
