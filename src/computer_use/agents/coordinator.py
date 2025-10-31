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
        Analyze user task using LLM and break it down into specific sub-tasks.

        Args:
            task: User's natural language task description

        Returns:
            TaskAnalysis with classification and specific sub-tasks for each agent
        """
        prompt = f"""
You are an intelligent task coordinator. Your job is to:
1. Analyze the overall task
2. Determine which agents are needed
3. Break down the task into SPECIFIC sub-tasks for each agent
4. Define clear objectives and expected outputs for each agent
5. If it is a simple conversational message or informational query that doesn't require automation:
   - Set requires_browser, requires_gui, requires_system all to false
   - Provide a friendly, helpful direct_response to answer the user
   - Be conversational, warm, and helpful in your response

Original Task: "{task}"

CRITICAL AGENT RESPONSIBILITIES - READ CAREFULLY:

Browser Agent - Web & Internet:
- Navigate websites, search, research, extract information
- Download files, extract data, take screenshots
- Fill web forms, handle signups/logins (including phone verification)
- Complete ENTIRE web workflows (signup, purchase, form submission)
- ONLY stops when web task is fully complete
- Does NOT interact with desktop applications

GUI Agent - Desktop Applications:
- Open and interact with ANY desktop application
- Click buttons, type text, copy/paste, scroll, navigate menus
- Handle ALL user interactions with apps (Calculator, Notes, Settings, ANY app)
- Use clipboard to copy results and paste into other apps
- EVERYTHING involving opening/using desktop apps = GUI Agent

System Agent - File System & Shell:
- File/folder operations via terminal (copy, move, delete, search)
- Shell commands that don't need GUI
- Use ONLY when task is purely file/folder management
- NOT for interacting with GUI applications

REASONING FRAMEWORK - Think Through These Questions:

Q1: What is the END GOAL?
→ What state should exist after completion?
→ What artifact/result/change should be observable?

Q2: What INPUTS are needed?
→ Does it need information from the internet? (Browser Agent)
→ Does it need files from the file system? (System Agent)
→ Does it need data from another app? (Depends on sequence)

Q3: What ACTIONS are required?
→ Visiting websites, extracting data, downloading? (Browser Agent)
→ Opening apps, clicking, typing, copying, pasting? (GUI Agent)
→ Creating folders, moving files, shell operations? (System Agent)

Q4: What is the NATURAL SEQUENCE?
→ Data must be gathered BEFORE it can be used
→ Files must exist BEFORE they can be opened
→ Results must be computed BEFORE they can be pasted

DECISION TREE:

Does task mention websites, search, research, download from web?
→ YES: requires_browser = true
→ Browser objective: What to find/download + where to save it
→ Browser output: The data/file that will be available for next agent

Does task involve desktop applications (any app with UI)?
→ YES: requires_gui = true
→ GUI objective: What app interactions needed + data flow between apps
→ GUI output: What will be visible/changed in the app

Does task involve ONLY file operations with no GUI needed?
→ YES: requires_system = true
→ System objective: What file/folder operations needed
→ System output: What files/folders will exist

CRITICAL THINKING PATTERNS:

Pattern: "Signup/Login to website X"
→ Browser ONLY (navigate, fill form, handle verification, complete signup)
→ NOT Browser + GUI! Browser handles the entire web workflow!

Pattern: "Download X from web"
→ Browser ONLY (navigate, find file, download to disk)

Pattern: "Get X from web and put in APP"
→ Browser: Get X → GUI: Open APP and use X

Pattern: "Calculate X in APP1 and show in APP2"  
→ GUI: Open APP1, compute X, copy result, open APP2, paste result
→ (Single GUI task - it handles multi-app workflows!)

Pattern: "Find file and do something with it"
→ System: Locate file → GUI: Open and interact with file

Pattern: "Research X"
→ Browser ONLY (gather and return data)

Now analyze this task and provide the breakdown:
"""

        # Use LLM with structured output
        structured_llm = self.llm_client.with_structured_output(TaskAnalysis)
        analysis = await structured_llm.ainvoke(prompt)

        return analysis
