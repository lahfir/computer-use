# Inter-Agent Communication System

## Overview

The system features robust CrewAI-powered inter-agent communication with intelligent task decomposition:

- **CrewAI Context Passing**: Automatic output passing between sequential tasks
- **Task Decomposition**: LLM-powered analysis breaks complex tasks into optimal subtasks
- **Structured Outputs**: Type-safe Pydantic schemas for all agent results
- **File Tracking**: Automatic discovery and path resolution for downloaded files
- **Principle-Based Intelligence**: Generic guidelines that scale to any task

---

## CrewAI Architecture

### Multi-Agent Orchestration

```python
from crewai import Agent, Task, Crew, Process

# Manager analyzes task and creates execution plan
task_plan = await orchestration_llm.decompose_task(user_request)

# Create CrewAI tasks with automatic context passing
tasks = []
for subtask in task_plan.subtasks:
    task = Task(
        description=subtask.description,
        expected_output=subtask.expected_output,
        agent=agents[subtask.agent_type],
        context=[tasks[-1]] if subtask.depends_on_previous else None,
    )
    tasks.append(task)

# Execute crew
crew = Crew(
    agents=list(agents.values()),
    tasks=tasks,
    process=Process.sequential,
    verbose=True,
)

result = crew.kickoff()
```

### Automatic Context Passing

CrewAI handles context passing between agents automatically:

```python
# Task 1: Browser downloads file
browser_task = Task(
    description="Download Tesla stock data from Yahoo Finance",
    agent=browser_agent,
    expected_output="CSV file with stock data",
    context=[],  # No previous context
)

# Task 2: GUI processes file (receives browser output automatically)
gui_task = Task(
    description="Open Excel and create chart from the downloaded data",
    agent=gui_agent,
    expected_output="Excel workbook with chart",
    context=[browser_task],  # ← CrewAI passes browser output here!
)
```

**What CrewAI Does**:
1. Browser agent executes and returns structured output
2. CrewAI captures the browser agent's result
3. GUI agent receives browser output in its context automatically
4. No manual serialization or context management needed

---

## Task Decomposition System

### How It Works

The Manager Agent uses structured LLM output to break down complex tasks:

```python
from pydantic import BaseModel, Field
from typing import List

class SubTask(BaseModel):
    """Single subtask in execution plan."""
    
    agent_type: str = Field(
        description="Agent type: 'browser', 'gui', or 'system'"
    )
    description: str = Field(
        description="Clear, specific task description"
    )
    expected_output: str = Field(
        description="What this agent should produce"
    )
    depends_on_previous: bool = Field(
        description="True if needs output from previous subtask"
    )

class TaskPlan(BaseModel):
    """Complete task execution plan."""
    
    reasoning: str = Field(
        description="Analysis of task and orchestration strategy"
    )
    subtasks: List[SubTask] = Field(
        description="List of subtasks in execution order"
    )
```

### Example Decomposition

**User Request**: "Download Nvidia stock report and create summary in TextEdit"

**Manager Agent Analysis**:
```python
TaskPlan(
    reasoning="Task requires web download followed by desktop app processing",
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Navigate to Yahoo Finance, search for Nvidia (NVDA), download quarterly report PDF",
            expected_output="PDF file with Nvidia stock report",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="gui",
            description="Open TextEdit and create a summary document using the downloaded PDF",
            expected_output="Text file with summary of key points",
            depends_on_previous=True  # Needs file path from browser
        )
    ]
)
```

**Execution Flow**:
```
Step 1: Browser Agent
  ↓
  Downloads nvidia_report.pdf to /tmp/browser_agent_xyz/
  ↓
  Returns: TaskCompletionOutput(
      success=True,
      files=["/tmp/browser_agent_xyz/nvidia_report.pdf"]
  )
  ↓
Step 2: CrewAI Context Passing
  ↓
  Automatically adds browser output to GUI task context
  ↓
Step 3: GUI Agent
  ↓
  Receives: context containing file path
  Opens TextEdit
  Creates summary using file path
  ↓
  Returns: TaskCompletionOutput(success=True)
```

---

## Type-Safe Data Structures

### TaskCompletionOutput Schema

All agents return this CrewAI-compatible structure:

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TaskCompletionOutput(BaseModel):
    """
    Structured output for CrewAI task completion.
    Used by all agents to return results.
    """
    
    success: bool = Field(
        description="Task completion status"
    )
    result: str = Field(
        description="Detailed result description"
    )
    files: List[str] = Field(
        default_factory=list,
        description="Paths to files created/downloaded"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional structured data"
    )
    next_steps: Optional[str] = Field(
        default=None,
        description="Suggested next actions"
    )
```

### BrowserOutput Schema

Browser agent uses enhanced output structure:

```python
from pydantic import BaseModel, Field

class FileDetail(BaseModel):
    """Metadata for a downloaded file."""
    path: str = Field(description="Absolute file path")
    name: str = Field(description="Filename")
    size: int = Field(description="Size in bytes")

class BrowserOutput(BaseModel):
    """
    Structured output from Browser agent.
    Embedded in TaskCompletionOutput.data field.
    """
    
    text: str = Field(
        description="Summary of actions and findings"
    )
    files: List[str] = Field(
        default_factory=list,
        description="Absolute paths to downloaded files"
    )
    file_details: List[FileDetail] = Field(
        default_factory=list,
        description="Detailed metadata for each file"
    )
    work_directory: Optional[str] = Field(
        default=None,
        description="Temporary working directory"
    )

    def format_summary(self) -> str:
        """Format comprehensive summary with file info."""
        summary = f"📝 Summary:\n{self.text}\n"
        if self.files:
            summary += "\n📁 DOWNLOADED FILES:\n"
            for file_path in self.files:
                summary += f"   • {file_path}\n"
            summary += "\n📊 File Details:\n"
            for fd in self.file_details:
                size_kb = fd.size / 1024
                summary += f"   • {fd.name} ({size_kb:.1f} KB)\n"
                summary += f"     Path: {fd.path}\n"
        return summary
```

### Agent Return Example

**Browser Agent**:
```python
# Browser agent returns TaskCompletionOutput
return TaskCompletionOutput(
    success=True,
    result="Downloaded Nvidia quarterly report from Yahoo Finance",
    files=["/tmp/browser_agent_abc/nvidia_q4_2024.pdf"],
    data={
        "output": BrowserOutput(
            text="Successfully downloaded Nvidia Q4 2024 report",
            files=["/tmp/browser_agent_abc/nvidia_q4_2024.pdf"],
            file_details=[
                FileDetail(
                    path="/tmp/browser_agent_abc/nvidia_q4_2024.pdf",
                    name="nvidia_q4_2024.pdf",
                    size=2359296  # 2.3 MB
                )
            ],
            work_directory="/tmp/browser_agent_abc"
        ).model_dump(),
        "stock_symbol": "NVDA",
        "report_quarter": "Q4 2024"
    },
    next_steps="File is ready for processing in desktop applications"
)
```

**GUI Agent**:
```python
# GUI agent returns TaskCompletionOutput
return TaskCompletionOutput(
    success=True,
    result="Created summary document in TextEdit",
    files=["/Users/john/Documents/nvidia_summary.txt"],
    data={
        "app_used": "TextEdit",
        "document_length": "450 words"
    }
)
```

---

## CrewAI Context Flow

### Sequential Task Execution

CrewAI executes tasks sequentially and passes context automatically:

```python
# Crew setup
crew = Crew(
    agents=[browser_agent, gui_agent, system_agent],
    tasks=[task1, task2, task3],
    process=Process.sequential,  # Tasks run in order
    verbose=True,
)

# Execution
# 1. task1 executes → returns output1
# 2. task2 receives output1 in context → returns output2
# 3. task3 receives output2 in context → returns output3
```

### Context Passing Example

**Real Workflow**: "Research census data and create presentation"

**Task 1 - Browser Agent**:
```python
browser_task = Task(
    description="Navigate to census.gov, search for demographic data, download 2024 population statistics",
    expected_output="CSV file with population data",
    agent=browser_agent,
    context=[],  # First task, no context
)

# Executes and returns:
TaskCompletionOutput(
    success=True,
    files=["/tmp/browser_agent_xyz/census_2024.csv"],
    result="Downloaded 2024 census data..."
)
```

**Task 2 - GUI Agent** (receives Task 1 output):
```python
gui_task = Task(
    description="Open Keynote, create presentation with census data from downloaded file",
    expected_output="Keynote presentation with charts",
    agent=gui_agent,
    context=[browser_task],  # ← Receives browser output!
)

# GUI agent sees in its context:
"""
Previous Task Output:
success: True
files: ["/tmp/browser_agent_xyz/census_2024.csv"]
result: "Downloaded 2024 census data..."
"""

# GUI agent can access the file path:
file_path = context["files"][0]  # "/tmp/browser_agent_xyz/census_2024.csv"

# Opens Keynote, imports CSV, creates charts
```

---

## Browser Agent Intelligence

### Principle-Based Guidelines

The Browser agent operates with clear boundaries:

```python
BROWSER_AGENT_GUIDELINES = """
🎯 BROWSER AGENT PRINCIPLES

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
"""
```

### Loop Prevention

```python
from browser_use import Agent, BrowserSession

agent = Agent(
    task=enhanced_task,
    llm=browser_llm,
    browser_session=browser_session,
    max_failures=5,      # Allow retries for network issues
)

# Hard limit prevents infinite loops
result = await agent.run(max_steps=30)
```

### Credential Handling

```python
CREDENTIALS_REMINDER = """
🚨 CRITICAL RULE: USE ONLY PROVIDED CREDENTIALS

❌ NEVER use test/placeholder data like:
   - test@gmail.com
   - placeholder@email.com
   - 123456 (fake phone)

✅ ALWAYS use EXACTLY what the user provides:
   - If task says "use email: user@example.com" → USE user@example.com
   - If task says "use phone: +1234567890" → USE +1234567890
   - If credentials NOT in task → Use tools (get_verification_phone_number, etc.)
"""
```

### QR Code Detection

```python
QR_CODE_HANDLING = """
📱 QR CODE INTELLIGENCE

Detection Signals:
- Images containing square QR code patterns
- Text like "Scan QR code", "Use your phone to scan"
- Two-factor authentication with QR option

Action:
→ QR CODE DETECTED: IMMEDIATELY call request_human_help
→ No automation possible - requires physical phone/device

Example:
request_human_help(
    reason="QR code authentication required",
    instructions="Please scan the QR code on screen with your mobile device"
)
"""
```

---

## File Tracking System

### Automatic Discovery

Browser agent automatically tracks downloaded files:

```python
async def track_downloaded_files(self, result: AgentHistoryList, temp_dir: Path):
    """
    Track files from Browser-Use execution.
    
    Sources:
    1. Browser-Use attachments field
    2. Files in working directory
    """
    downloaded_files = []
    file_details = []
    
    # Check Browser-Use attachments
    if result.history and len(result.history) > 0:
        attachments = result.history[-1].result[-1].attachments
        if attachments:
            for attachment in attachments:
                path = Path(attachment)
                if path.exists():
                    downloaded_files.append(str(path.absolute()))
                    file_details.append(FileDetail(
                        path=str(path.absolute()),
                        name=path.name,
                        size=path.stat().st_size
                    ))
    
    # Scan browser working directory
    browser_data_dir = temp_dir / "browseruse_agent_data"
    if browser_data_dir.exists():
        for file_path in browser_data_dir.rglob("*"):
            if file_path.is_file():
                downloaded_files.append(str(file_path.absolute()))
                file_details.append(FileDetail(
                    path=str(file_path.absolute()),
                    name=file_path.name,
                    size=file_path.stat().st_size
                ))
    
    return downloaded_files, file_details
```

### Path Resolution

All file paths are converted to absolute paths:

```python
# Relative path → Absolute path
"/tmp/browseruse_agent_data/report.pdf"
→ "/tmp/browser_agent_abc123/browseruse_agent_data/report.pdf"

# GUI agent receives absolute path in context
# Can directly open file without path resolution
```

---

## GUI Agent Context Display

### Rich Context Formatting

The GUI agent receives beautifully formatted context:

```python
def format_context_for_gui(self, context: Dict[str, Any]) -> str:
    """Format context for GUI agent prompt."""
    
    if not context or not context.get("previous_results"):
        return ""
    
    context_str = """
============================================================
PREVIOUS AGENT WORK (Build on this!):
============================================================

"""
    
    for i, result in enumerate(context["previous_results"], 1):
        agent_type = result.get("method_used", "unknown")
        action = result.get("action_taken", "")
        success = "✅" if result.get("success") else "❌"
        
        context_str += f"{success} Agent {i} ({agent_type}): {action}\n"
        
        # Parse browser output if available
        if result.get("data") and "output" in result["data"]:
            output_data = result["data"]["output"]
            if isinstance(output_data, dict):
                try:
                    browser_output = BrowserOutput(**output_data)
                    context_str += f"\n📝 Summary:\n{browser_output.text}\n"
                    
                    if browser_output.has_files():
                        context_str += "\n📁 DOWNLOADED FILES (use these paths!):\n"
                        for file_path in browser_output.files:
                            context_str += f"   • {file_path}\n"
                        
                        context_str += "\n📊 File Details:\n"
                        for fd in browser_output.file_details:
                            size_kb = fd.size / 1024
                            context_str += f"   • {fd.name} ({size_kb:.1f} KB)\n"
                            context_str += f"     Path: {fd.path}\n"
                except Exception:
                    pass
    
    context_str += """
============================================================
🎯 YOUR JOB: Use the files/data above to complete the current task!
============================================================
"""
    
    return context_str
```

**Rendered Example**:
```
============================================================
PREVIOUS AGENT WORK (Build on this!):
============================================================

✅ Agent 1 (browser): Downloaded census demographic data

📝 Summary:
Successfully downloaded 2024 demographic data from census.gov

📁 DOWNLOADED FILES (use these paths!):
   • /tmp/browser_agent_abc/demographics_2024.csv

📊 File Details:
   • demographics_2024.csv (524.0 KB)
     Path: /tmp/browser_agent_abc/demographics_2024.csv

============================================================
🎯 YOUR JOB: Use the files/data above to complete the current task!
============================================================
```

---

## Conversation Memory

### Rolling Context Window

The system maintains conversation history:

```python
# In main.py
conversation_history = []

while True:
    task = await get_task_input()
    
    # Execute with conversation context
    result = await crew.execute_task(task, conversation_history)
    
    # Store interaction
    conversation_history.append({
        "user": task,
        "result": result
    })
    
    # Keep last 10 interactions
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]
```

### Context-Aware Responses

The Manager agent can provide direct responses for conversational queries:

```python
# User: "What did you just download?"
# Manager analyzes conversation history
# Finds previous task result
# Returns direct response without agent execution

if is_conversational_query(task):
    return TaskExecutionResult(
        task=task,
        overall_success=True,
        result=generate_response_from_history(conversation_history),
        error=None
    )
```

---

## Example Workflows

### Workflow 1: Download & Process

**User**: "Download Tesla stock data and create chart in Excel"

**Decomposition**:
```python
TaskPlan(
    reasoning="Requires web download followed by desktop processing",
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Navigate to Yahoo Finance, download Tesla stock data for last 30 days",
            expected_output="CSV with stock prices",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="gui",
            description="Open Excel, import CSV, create line chart of stock prices",
            expected_output="Excel workbook with chart",
            depends_on_previous=True
        )
    ]
)
```

**Execution**:
1. Browser: Downloads `tesla_stock.csv` → `/tmp/browser_agent_xyz/tesla_stock.csv`
2. CrewAI: Passes file path in context
3. GUI: Opens Excel, imports `/tmp/browser_agent_xyz/tesla_stock.csv`, creates chart
4. Result: Excel workbook saved

### Workflow 2: Research & Document

**User**: "Research AI trends on news sites and create summary document"

**Decomposition**:
```python
TaskPlan(
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Visit tech news sites, extract AI trend articles, save key points",
            expected_output="Text file with extracted information",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="gui",
            description="Open TextEdit, create formatted document with research findings",
            expected_output="Text document with summary",
            depends_on_previous=True
        )
    ]
)
```

### Workflow 3: Multi-Step File Operation

**User**: "Download report and move it to Documents with today's date in filename"

**Decomposition**:
```python
TaskPlan(
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Download quarterly report PDF",
            expected_output="PDF file",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="system",
            description="Move downloaded PDF to Documents folder, rename with today's date",
            expected_output="File moved and renamed",
            depends_on_previous=True
        )
    ]
)
```

**Execution**:
1. Browser: Downloads to `/tmp/browser_agent_xyz/report.pdf`
2. CrewAI: Passes path
3. System: `mv /tmp/browser_agent_xyz/report.pdf ~/Documents/report_2025-01-15.pdf`

---

## Benefits of CrewAI Architecture

### Automatic Context Management

| Feature | CrewAI | Manual Approach |
|---------|--------|-----------------|
| Context Passing | Automatic | Manual serialization |
| Type Safety | Built-in | Custom implementation |
| Task Chaining | Sequential process | Custom orchestration |
| Error Handling | Framework-level | Manual try/catch |
| Memory | Built-in support | Custom storage |

### Intelligent Task Decomposition

- **Adaptive**: LLM analyzes each unique request
- **Optimal**: Minimizes steps while ensuring success
- **Context-Aware**: Considers conversation history
- **Scalable**: Works with any complexity level

### Type-Safe Communication

- **Pydantic Schemas**: Compile-time type checking
- **IDE Support**: Full autocomplete
- **Validation**: Automatic data validation
- **Documentation**: Self-documenting schemas

---

## Future Enhancements

### Parallel Execution

```python
# Currently sequential
process=Process.sequential

# Future: Parallel for independent tasks
process=Process.parallel
```

### Persistent Memory

```python
# CrewAI memory feature
crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,  # Agents remember across sessions
)
```

### Entity Knowledge Base

```python
from crewai import Entity

# Structured knowledge storage
nvidia = Entity(
    name="Nvidia Corporation",
    stock_symbol="NVDA",
    last_price=195.21,
    updated="2025-01-15"
)
```

---

## Summary

✅ **CrewAI Orchestration**: Professional multi-agent coordination  
✅ **Task Decomposition**: LLM-powered intelligent planning  
✅ **Automatic Context**: No manual serialization needed  
✅ **Type Safety**: Pydantic schemas throughout  
✅ **File Tracking**: Automatic path discovery and resolution  
✅ **Principle-Based**: Scalable agent guidelines  

**The system leverages CrewAI's powerful orchestration to provide enterprise-grade automation!** 🚀
