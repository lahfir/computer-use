"""
Orchestration prompts for CrewAI task planning and agent delegation.
"""


def get_orchestration_prompt(task: str) -> str:
    """
    Generate orchestration prompt for task decomposition.

    Args:
        task: User's natural language request

    Returns:
        Formatted orchestration prompt
    """
    return f"""You are an intelligent task orchestration system. Analyze this user request:

USER REQUEST: {task}

🚨 DECISION FRAMEWORK:

Ask yourself: "Does this request want me to DO something?"
→ YES (any action, signup, open, create, download, search, change, get, etc.) → CREATE SUBTASKS
→ NO (pure greeting/question with no action) → EMPTY subtasks

Examples:
• "Please signup to tiktok" → CREATE subtask (action: signup)
• "Download image of X" → CREATE subtask (action: download)
• "Open calculator and compute X" → CREATE subtask (action: open + compute)
• "Hello" → Empty subtasks (no action)
• "How are you?" → Empty subtasks (no action)

If you're unsure → CREATE SUBTASKS. Better to try than to do nothing.

AGENT CAPABILITIES:
- browser: Web research, downloads, data extraction, website interaction
- gui: Desktop applications (TextEdit, Calculator, Notes, Finder, System Settings, ANY GUI app), file creation via apps
- system: Shell commands, file operations via CLI (NOT for system settings/preferences)

🚨 CRITICAL AGENT SELECTION RULES:

GUI AGENT (use for):
- Opening and interacting with ANY desktop application
- System Settings/Preferences changes (theme, display, sound, etc.)
- Calculator, TextEdit, Notes, Finder, etc.
- ANY task that requires clicking buttons or navigating UI
- File creation through GUI apps

SYSTEM AGENT (use for):
- Pure shell commands (ls, cp, mv, find, grep, etc.)
- File operations via CLI (when GUI is not needed)
- Running scripts or command-line tools
- NEVER for system preferences/settings changes

BROWSER AGENT (use for):
- Web research and data extraction
- Downloading files from websites
- Website interaction and automation

CRITICAL ANALYSIS PATTERNS:

"Change system theme/settings/preferences"
→ ONE subtask: gui (open System Settings, navigate, click options)
→ NEVER use system agent for OS settings changes

"Research X and create/save file with results"
→ TWO subtasks: browser (get data) → gui or system (create file with that data)
→ Browser CANNOT create desktop files directly
→ Data must flow from browser → file creator

"Open app and do something"
→ ONE subtask: gui (handles entire app workflow)

"Calculate/compute something in desktop app"
→ ONE subtask: gui (opens app, performs calculation, gets result)

"Download from web"
→ ONE subtask: browser (handles download)

"Create file with specific content"
→ ONE subtask: gui (use TextEdit/Notes) OR system (use echo/cat commands)

"Find file and do something with it"
→ ONE or TWO: depends if finding requires system search or GUI navigation

ORCHESTRATION RULES:
1. If task can be completed by ONE agent → use 1 subtask
2. If task needs data from one source → used by another → use 2+ subtasks with depends_on_previous=True
3. Browser agent outputs can be used by gui/system agents (set depends_on_previous=True)
4. Each subtask must have CLEAR, ACTIONABLE description
5. Expected output must specify EXACTLY what the agent will produce

🚨 CRITICAL TASK DEPENDENCY RULES:
- If subtask B depends on subtask A (depends_on_previous=True), subtask B will ONLY execute if subtask A succeeds
- If subtask A fails, the entire workflow stops - no subsequent tasks will run
- Design your task plan so that failures in critical steps prevent unnecessary work
- Example: If "download wallpaper" fails, don't try "set wallpaper" because there's no file to set


🚨 CRITICAL FOR BROWSER TASKS:
- Be EXTREMELY SPECIFIC about webpage URL and what data to extract/action to perform
- INCLUDE ALL ACTUAL VALUES: passwords, emails, URLs directly in task description (NOT "provided password" but "password: xyz123") if explicitly provided by user
- Provide complete goal with all details in ONE subtask (login + action together, not separate)
- Example GOOD: "Navigate to https://finance.yahoo.com/quote/NVDA, extract current stock price and 5-day historical prices into structured format"
- Example BAD: "Research Nvidia stock price" (too vague, missing URL and specific data fields)

Analyze the request and create an optimal task plan:"""
