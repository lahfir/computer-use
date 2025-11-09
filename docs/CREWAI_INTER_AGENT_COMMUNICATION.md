# CrewAI Inter-Agent Communication System

## Overview

This document explains how agents communicate and share data in our CrewAI-powered computer automation system.

The system uses CrewAI's native task orchestration with automatic context passing, intelligent task decomposition, and structured outputs for seamless multi-agent collaboration.

---

## CrewAI Architecture

### What We Use

Our system is built on **CrewAI (v0.86.0+)** with the following architecture:

- **Manager Agent**: LLM-powered task decomposition and agent delegation
- **Specialist Agents**: Browser, GUI, and System agents with specific expertise
- **Sequential Execution**: Tasks run in order with automatic context passing
- **Structured Outputs**: Pydantic schemas for type-safe communication

### What Changed from Old Architecture

**Before** (Custom Coordinator):

```python
# ❌ Manual string concatenation
context = {"task": task, "previous_results": []}
context_str = str(context)  # Converting to string manually
```

**After** (CrewAI):

```python
# ✅ CrewAI native context passing
browser_task = Task(
    description="Download file...",
    agent=browser_agent,
    context=[],
)

gui_task = Task(
    description="Process file...",
    agent=gui_agent,
    context=[browser_task],  # ← CrewAI handles output passing automatically!
)
```

**Benefits**:

- ✅ Automatic context management
- ✅ Type-safe outputs via Pydantic
- ✅ Professional orchestration framework
- ✅ Built-in memory and learning capabilities
- ✅ Sequential task execution with dependencies

---

## Task Decomposition System

### LLM-Powered Planning

The Manager Agent uses an LLM to analyze tasks and create optimal execution plans:

```python
from pydantic import BaseModel, Field
from typing import List

class SubTask(BaseModel):
    """Single subtask in execution plan."""

    agent_type: str = Field(
        description="Agent type: 'browser', 'gui', or 'system'"
    )
    description: str = Field(
        description="Clear, specific task description for this agent"
    )
    expected_output: str = Field(
        description="What this agent should produce"
    )
    depends_on_previous: bool = Field(
        description="True if this subtask needs output from previous subtask"
    )

class TaskPlan(BaseModel):
    """Complete task execution plan."""

    reasoning: str = Field(
        description="Analysis of the task and orchestration strategy"
    )
    subtasks: List[SubTask] = Field(
        description="List of subtasks in execution order",
        min_length=0,  # Can be empty for conversational queries
    )
```

### Decomposition Example

**User Request**: "Download Nvidia report and create summary in TextEdit"

**Manager Agent Output**:

```python
TaskPlan(
    reasoning="Task requires web download followed by desktop app processing",
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Navigate to Yahoo Finance, search for Nvidia (NVDA), download quarterly report",
            expected_output="PDF file with Nvidia quarterly report",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="gui",
            description="Open TextEdit and create a summary document from the downloaded PDF",
            expected_output="Text file with summary of key report points",
            depends_on_previous=True  # ← Needs file path from browser
        )
    ]
)
```

### CrewAI Crew Creation

```python
from crewai import Agent, Task, Crew, Process

# Create CrewAI agents (defined in agents.yaml)
agents_dict = self._create_crewai_agents()

crew_agents = []
crew_tasks = []

# Build tasks from decomposition plan
for idx, subtask in enumerate(plan.subtasks):
    # Get appropriate agent
    agent_key = f"{subtask.agent_type}_agent"
    agent = agents_dict[agent_key]
    crew_agents.append(agent)

    # Create CrewAI Task with context dependency
    task = Task(
        description=subtask.description,
        expected_output=subtask.expected_output,
        agent=agent,
        output_pydantic=TaskCompletionOutput,  # Structured output
        context=(
            [crew_tasks[-1]]  # Previous task for context
            if subtask.depends_on_previous and crew_tasks
            else None
        ),
    )
    crew_tasks.append(task)

# Create and execute Crew
self.crew = Crew(
    agents=list(set(crew_agents)),  # Unique agents
    tasks=crew_tasks,
    process=Process.sequential,  # Sequential execution
    verbose=True,
)

# Execute
result = await loop.run_in_executor(None, self.crew.kickoff)
```

---

## Automatic Context Passing

### How CrewAI Handles Context

CrewAI automatically passes task outputs between sequential tasks:

```python
# Task 1: Browser downloads file
browser_task = Task(
    description="Download Nvidia report from Yahoo Finance",
    agent=browser_agent,
    expected_output="PDF file",
    context=[],  # No previous tasks
)

# Task 2: GUI processes file
gui_task = Task(
    description="Create summary in TextEdit",
    agent=gui_agent,
    expected_output="Text summary",
    context=[browser_task],  # ← Gets browser_task output automatically!
)

# When gui_task executes, it receives:
# - browser_task's TaskCompletionOutput
# - File paths from browser_task.files
# - Any data from browser_task.data
```

**What CrewAI Does Automatically**:

1. Captures browser agent's output (TaskCompletionOutput)
2. Serializes output to string format
3. Injects output into GUI agent's task description
4. GUI agent can access file paths and data

### Context Format

When Task 2 receives context from Task 1, CrewAI injects it as:

```
Task 2 Description: Create summary in TextEdit

Context from previous task:
success: True
result: Downloaded Nvidia quarterly report from Yahoo Finance
files: ["/tmp/browser_agent_xyz/nvidia_q4_2024.pdf"]
data: {
  "stock_symbol": "NVDA",
  "file_size": "2.3MB"
}
```

---

## Structured Output Format

### TaskCompletionOutput Schema

All agents return this Pydantic schema:

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TaskCompletionOutput(BaseModel):
    """
    Structured output for CrewAI task completion.
    Returned by all specialist agents.
    """

    success: bool = Field(
        description="Task completion status"
    )
    result: str = Field(
        description="Detailed result description"
    )
    files: List[str] = Field(
        default_factory=list,
        description="Paths to files created/downloaded (absolute paths)"
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

**Benefits**:

- ✅ Type-safe with Pydantic validation
- ✅ Consistent across all agents
- ✅ CrewAI-compatible
- ✅ IDE autocomplete support

### Example Agent Returns

**Browser Agent**:

```python
TaskCompletionOutput(
    success=True,
    result="Downloaded Nvidia Q4 2024 quarterly report from Yahoo Finance",
    files=["/tmp/browser_agent_abc123/nvidia_q4_2024.pdf"],
    data={
        "output": BrowserOutput(...).model_dump(),  # Enhanced browser data
        "stock_symbol": "NVDA",
        "report_quarter": "Q4 2024",
        "file_size_mb": 2.3
    },
    next_steps="File is ready for processing in desktop applications"
)
```

**GUI Agent**:

```python
TaskCompletionOutput(
    success=True,
    result="Created summary document in TextEdit with key report highlights",
    files=["/Users/john/Documents/nvidia_summary.txt"],
    data={
        "app_used": "TextEdit",
        "document_length": "450 words",
        "summary_sections": ["Revenue", "Earnings", "Outlook"]
    }
)
```

**System Agent**:

```python
TaskCompletionOutput(
    success=True,
    result="Moved file to Documents with date-stamped filename",
    files=["/Users/john/Documents/report_2025-01-15.pdf"],
    data={
        "command_executed": "mv /tmp/report.pdf ~/Documents/report_2025-01-15.pdf",
        "original_path": "/tmp/report.pdf",
        "new_path": "/Users/john/Documents/report_2025-01-15.pdf"
    }
)
```

---

## File Path Sharing

### Automatic File Tracking

Browser agent automatically tracks all downloaded files:

```python
async def track_files(self, result: AgentHistoryList, temp_dir: Path):
    """Track files from Browser-Use execution."""

    downloaded_files = []
    file_details = []

    # 1. Check Browser-Use attachments
    if result.history:
        attachments = result.history[-1].result[-1].attachments
        for attachment in attachments:
            path = Path(attachment)
            if path.exists():
                downloaded_files.append(str(path.absolute()))
                file_details.append({
                    "name": path.name,
                    "size": path.stat().st_size
                })

    # 2. Scan working directory
    browser_data_dir = temp_dir / "browseruse_agent_data"
    if browser_data_dir.exists():
        for file_path in browser_data_dir.rglob("*"):
            if file_path.is_file():
                downloaded_files.append(str(file_path.absolute()))

    return downloaded_files, file_details
```

### Path Resolution

**All paths are absolute**:

```python
# ❌ Relative path (can break)
"report.pdf"

# ✅ Absolute path (always works)
"/tmp/browser_agent_abc123/browseruse_agent_data/report.pdf"
```

**Benefits**:

- Next agent can directly access files
- No path resolution needed
- Works across different working directories
- Platform-agnostic (macOS, Windows, Linux)

### File Sharing Example

```python
# Browser agent downloads and returns
TaskCompletionOutput(
    files=["/tmp/browser_agent_xyz/stock_data.csv"]
)

# CrewAI passes to GUI agent
# GUI agent receives in context:
"""
files: ["/tmp/browser_agent_xyz/stock_data.csv"]
"""

# GUI agent can directly use the path:
file_path = "/tmp/browser_agent_xyz/stock_data.csv"
# Opens Excel and imports file
```

---

## Real-World Example

### Complete Workflow

**User Request**: "Research Tesla stock data and create Excel chart"

**Step 1: Manager Agent Decomposes Task**

```python
TaskPlan(
    reasoning="Task requires web research followed by desktop processing",
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Navigate to Yahoo Finance, extract Tesla (TSLA) stock data for last 30 days including dates, prices, and volumes",
            expected_output="CSV file with stock data",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="gui",
            description="Open Excel, import the CSV file, create a line chart showing stock price trend over time",
            expected_output="Excel workbook with formatted chart",
            depends_on_previous=True
        )
    ]
)
```

**Step 2: Browser Agent Executes**

```python
# Browser agent navigates to Yahoo Finance
# Downloads stock data
# Returns structured output

TaskCompletionOutput(
    success=True,
    result="Downloaded Tesla stock data for last 30 days from Yahoo Finance",
    files=["/tmp/browser_agent_abc/tesla_stock.csv"],
    data={
        "output": BrowserOutput(
            text="Successfully extracted Tesla stock data",
            files=["/tmp/browser_agent_abc/tesla_stock.csv"],
            file_details=[FileDetail(
                path="/tmp/browser_agent_abc/tesla_stock.csv",
                name="tesla_stock.csv",
                size=15360  # 15 KB
            )],
            work_directory="/tmp/browser_agent_abc"
        ).model_dump(),
        "stock_symbol": "TSLA",
        "date_range": "2024-12-15 to 2025-01-15",
        "data_points": 30
    },
    next_steps="Data ready for analysis in Excel or other tools"
)
```

**Step 3: CrewAI Passes Context**

CrewAI automatically injects browser output into GUI task:

```
Task: Open Excel, import the CSV file, create a line chart showing stock price trend

Context from previous task:
success: True
result: Downloaded Tesla stock data for last 30 days from Yahoo Finance
files: ["/tmp/browser_agent_abc/tesla_stock.csv"]
data: {
  "stock_symbol": "TSLA",
  "date_range": "2024-12-15 to 2025-01-15",
  "data_points": 30
}
```

**Step 4: GUI Agent Executes**

```python
# GUI agent sees file path in context
# Opens Excel
# Imports /tmp/browser_agent_abc/tesla_stock.csv
# Creates chart
# Returns completion

TaskCompletionOutput(
    success=True,
    result="Created Excel workbook with Tesla stock price chart",
    files=["/Users/john/Documents/tesla_chart.xlsx"],
    data={
        "app_used": "Microsoft Excel",
        "chart_type": "line",
        "data_points_plotted": 30
    }
)
```

**Step 5: Final Result**

```python
# Aggregated by CrewAI
{
    "task": "Research Tesla stock data and create Excel chart",
    "overall_success": True,
    "result": "Task completed successfully across 2 agents",
    "agent_results": [
        # Browser agent result
        # GUI agent result
    ]
}
```

---

## Enhanced Browser Output

### BrowserOutput Schema

Browser agent uses enhanced output for file tracking:

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class FileDetail(BaseModel):
    """Metadata for a single downloaded file."""
    path: str = Field(description="Absolute file path")
    name: str = Field(description="Filename")
    size: int = Field(description="Size in bytes")

class BrowserOutput(BaseModel):
    """Enhanced structured output from Browser agent."""

    text: str = Field(
        description="Summary of actions and findings"
    )
    files: List[str] = Field(
        default_factory=list,
        description="Absolute paths to all downloaded files"
    )
    file_details: List[FileDetail] = Field(
        default_factory=list,
        description="Detailed metadata for each file"
    )
    work_directory: Optional[str] = Field(
        default=None,
        description="Browser agent's temporary working directory"
    )

    def has_files(self) -> bool:
        """Check if any files were downloaded."""
        return len(self.files) > 0

    def get_file_count(self) -> int:
        """Get number of downloaded files."""
        return len(self.files)

    def get_total_size_kb(self) -> float:
        """Get total size of all files in KB."""
        return sum(f.size for f in self.file_details) / 1024

    def format_summary(self) -> str:
        """Format comprehensive summary with file information."""
        summary = f"📝 Summary:\n{self.text}\n"

        if self.has_files():
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

**Usage**:

```python
# Browser agent creates enhanced output
browser_output = BrowserOutput(
    text="Downloaded stock data",
    files=["/tmp/browser_agent_xyz/data.csv"],
    file_details=[FileDetail(
        path="/tmp/browser_agent_xyz/data.csv",
        name="data.csv",
        size=15360
    )],
    work_directory="/tmp/browser_agent_xyz"
)

# Embed in TaskCompletionOutput
return TaskCompletionOutput(
    success=True,
    result=browser_output.text,
    files=browser_output.files,
    data={"output": browser_output.model_dump()}
)

# Next agent can parse it
if isinstance(data["output"], dict):
    browser_output = BrowserOutput(**data["output"])
    print(browser_output.format_summary())
```

---

## Agent Configuration

### agents.yaml

Agents are configured in YAML with roles, goals, and tools:

```yaml
browser_agent:
  role: Web Automation Specialist
  goal: Navigate websites, download files, fill forms
  backstory: |
    You are a web automation specialist using Browser-Use.
    Your ONLY tool is 'web_automation'.
  tools:
    - web_automation
  max_iter: 20
  verbose: true

gui_agent:
  role: Desktop Application Automation Expert
  goal: Automate any desktop application
  backstory: |
    You are a desktop automation expert.
    Use multi-tier accuracy system (accessibility → OCR → vision).
  tools:
    - open_application
    - get_accessible_elements
    - click_element
    - type_text
    - read_screen_text
    - get_app_text
    - scroll
    - get_window_image
    - find_application
    - request_human_input
  max_iter: 25
  verbose: true

system_agent:
  role: System Command & Terminal Expert
  goal: Execute commands and file operations safely
  backstory: |
    You MUST use execute_shell_command tool.
    You have NO other capability.
  tools:
    - execute_shell_command
  max_iter: 10
  verbose: true
```

---

## Benefits of CrewAI System

### vs. Custom Coordinator

| Feature            | CrewAI               | Custom Coordinator       |
| ------------------ | -------------------- | ------------------------ |
| Context Passing    | ✅ Automatic         | ❌ Manual serialization  |
| Type Safety        | ✅ Built-in          | ❌ Custom implementation |
| Task Decomposition | ✅ LLM-powered       | ❌ Hardcoded rules       |
| Memory             | ✅ Framework support | ❌ Custom storage        |
| Error Handling     | ✅ Framework-level   | ❌ Manual try/catch      |
| Scalability        | ✅ Add agents easily | ❌ Rewrite coordinator   |

### Key Advantages

1. **Professional Framework**: Battle-tested orchestration
2. **Automatic Context**: No manual string concatenation
3. **Intelligent Decomposition**: LLM analyzes each task uniquely
4. **Type Safety**: Pydantic schemas throughout
5. **Easy Extension**: Add new agents without core changes
6. **Built-in Features**: Memory, learning, delegation

---

## Future Enhancements

### Parallel Execution

```python
# Currently: Sequential
process=Process.sequential

# Future: Parallel for independent tasks
process=Process.parallel
```

**Use Case**: Download multiple files simultaneously

### Persistent Memory

```python
# CrewAI memory feature
crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,  # ← Agents remember across sessions
)
```

**Use Case**: Remember user preferences and past interactions

### Entity Knowledge Base

```python
from crewai import Entity

# Structured knowledge storage
tesla = Entity(
    name="Tesla Inc.",
    stock_symbol="TSLA",
    last_price=195.21,
    industry="Automotive",
    last_updated="2025-01-15"
)
```

**Use Case**: Build knowledge graph of entities

---

## Summary

✅ **CrewAI Orchestration**: Professional multi-agent framework  
✅ **Automatic Context**: CrewAI handles output passing between tasks  
✅ **Task Decomposition**: LLM-powered intelligent planning  
✅ **Structured Outputs**: Type-safe Pydantic schemas  
✅ **File Tracking**: Automatic path discovery and absolute paths  
✅ **Scalable Architecture**: Easy to add new agents and capabilities

**The system leverages CrewAI's powerful orchestration to eliminate manual context management and enable intelligent multi-agent collaboration!** 🚀
