# Computer Use Agent - Technical Reference

> **Last Updated**: January 2025  
> **Purpose**: Comprehensive technical reference for CrewAI-based architecture, implementation patterns, and development guidelines

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [CrewAI Architecture](#crewai-architecture)
3. [Task Decomposition System](#task-decomposition-system)
4. [Agent Implementation](#agent-implementation)
5. [Inter-Agent Communication](#inter-agent-communication)
6. [Platform-Specific Implementation](#platform-specific-implementation)
7. [Multi-Tier Accuracy System](#multi-tier-accuracy-system)
8. [CrewAI Tools](#crewai-tools)
9. [Type Safety & Schemas](#type-safety--schemas)
10. [Configuration](#configuration)
11. [Development Standards](#development-standards)

---

## Project Overview

### Purpose

A CrewAI-powered multi-agent autonomous desktop and web automation system featuring:

- **CrewAI Orchestration**: Manager agent with intelligent task decomposition
- **Browser Automation**: Web tasks via Browser-Use (downloads, forms, research)
- **GUI Automation**: Desktop applications with multi-tier accuracy
- **System Automation**: Terminal commands and file operations
- **Phone Verification**: Twilio SMS integration for account signups

### Core Technology Stack

- **CrewAI (v0.86.0+)**: Multi-agent orchestration framework
- **Browser-Use (v0.9.4+)**: Web automation engine
- **LangChain**: LLM framework for structured outputs
- **Platform Accessibility**:
  - macOS: atomacos, NSAccessibility API
  - Windows: pywinauto, UI Automation API
  - Linux: python3-pyatspi, AT-SPI protocol
- **Computer Vision**: EasyOCR, PaddleOCR, macOS Vision, OpenCV
- **Vision LLMs**: GPT-4V, Claude 3.5 Sonnet, Gemini 2.0 Flash

### Supported Platforms

- **macOS**: 10.14 (Mojave) or higher - Full support with NSAccessibility
- **Windows**: 10 or higher - Full support with UI Automation
- **Linux**: Ubuntu 20.04+, Debian 11+ - Full support with AT-SPI

---

## CrewAI Architecture

### System Design

```
User Request
    ↓
┌─────────────────────────────────────────┐
│     Manager Agent (Task Decomposition)  │
│  ┌───────────────────────────────────┐ │
│  │  LLM analyzes request             │ │
│  │  Decomposes into subtasks         │ │
│  │  Selects specialist agents        │ │
│  │  Creates execution plan           │ │
│  └───────────────────────────────────┘ │
└─────────────────┬───────────────────────┘
                  │
          ┌───────┴────────┬──────────┐
          ↓                ↓          ↓
    ┌──────────┐    ┌──────────┐  ┌──────────┐
    │ Browser  │    │   GUI    │  │  System  │
    │  Agent   │    │  Agent   │  │  Agent   │
    └────┬─────┘    └────┬─────┘  └────┬─────┘
         │               │             │
         ↓               ↓             ↓
    CrewAI Task    CrewAI Task    CrewAI Task
    (Sequential execution with context passing)
         │               │             │
         ↓               ↓             ↓
    Results aggregated by CrewAI
         │
         ↓
    User receives final output
```

### Agent Hierarchy

**Manager Agent**:

- Role: Task Orchestration Manager
- Responsibilities:
  - Analyze user requests
  - Decompose into subtasks
  - Select appropriate agents
  - Manage execution flow
- Tool: No tools (delegation only)
- LLM: Standard LLM (GPT-4, Claude, Gemini)

**Browser Agent**:

- Role: Web Automation Specialist
- Responsibilities:
  - Web navigation and interaction
  - File downloads
  - Data extraction
  - Form filling
  - Phone verification
- Tools: `web_automation`
- LLM: Browser-Use compatible LLM

**GUI Agent**:

- Role: Desktop Application Automation Expert
- Responsibilities:
  - Desktop app control
  - Multi-tier element detection
  - Mouse and keyboard automation
  - Screenshot-driven workflows
- Tools: 13 GUI tools (click, type, screenshot, etc.)
- LLM: Vision-capable LLM

**System Agent**:

- Role: System Command & Terminal Expert
- Responsibilities:
  - Terminal command execution
  - File operations
  - Process management
  - System-level tasks
- Tools: `execute_shell_command`
- LLM: Standard LLM

---

## Task Decomposition System

### How It Works

The Manager Agent uses structured LLM output to decompose tasks:

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

### Decomposition Prompt

The Manager Agent receives a comprehensive prompt:

```python
orchestration_prompt = f"""
You are an intelligent task orchestration system.

USER REQUEST: {task}

🚨 DECISION FRAMEWORK:
Ask yourself: "Does this request want me to DO something?"
→ YES (any action) → CREATE SUBTASKS
→ NO (pure greeting) → EMPTY subtasks

AGENT CAPABILITIES:
- browser: Web research, downloads, data extraction, website interaction
- gui: Desktop applications (Calculator, TextEdit, System Settings, ANY GUI app)
- system: Shell commands, file operations via CLI

CRITICAL AGENT SELECTION RULES:

GUI AGENT (use for):
- Opening and interacting with ANY desktop application
- System Settings/Preferences changes
- File creation through GUI apps

SYSTEM AGENT (use for):
- Pure shell commands (ls, cp, mv, find, grep)
- File operations via CLI
- NEVER for system preferences/settings

BROWSER AGENT (use for):
- Web research and data extraction
- Downloading files from websites
- Website interaction and automation

ORCHESTRATION RULES:
1. If task can be completed by ONE agent → use 1 subtask
2. If task needs data from one source used by another → use 2+ subtasks with depends_on_previous=True
3. Each subtask must have CLEAR, ACTIONABLE description

Analyze the request and create an optimal task plan.
"""
```

### Example Decomposition

**Request**: "Download Tesla stock data and create chart in Excel"

**Manager Agent Output**:

```python
TaskPlan(
    reasoning="Task requires web data download followed by desktop app processing",
    subtasks=[
        SubTask(
            agent_type="browser",
            description="Navigate to Yahoo Finance, search for Tesla (TSLA), extract current price and 5-day historical data",
            expected_output="CSV file with Tesla stock data including dates, prices, volumes",
            depends_on_previous=False
        ),
        SubTask(
            agent_type="gui",
            description="Open Excel, import the downloaded CSV file, create a line chart of stock prices over time",
            expected_output="Excel workbook with formatted chart showing Tesla stock trends",
            depends_on_previous=True  # Needs file from browser agent
        )
    ]
)
```

### CrewAI Crew Creation

```python
from crewai import Agent, Task, Crew, Process

# Create CrewAI agents
agents_dict = self._create_crewai_agents()  # Returns dict of agent instances

crew_agents = []
crew_tasks = []

for idx, subtask in enumerate(plan.subtasks):
    # Get appropriate agent
    agent_key = f"{subtask.agent_type}_agent"
    agent = agents_dict[agent_key]
    crew_agents.append(agent)

    # Create CrewAI Task
    crew_task = Task(
        description=subtask.description,
        expected_output=subtask.expected_output,
        agent=agent,
        output_pydantic=TaskCompletionOutput,
        context=(
            [crew_tasks[-1]]  # Previous task output
            if subtask.depends_on_previous and crew_tasks
            else None
        ),
    )
    crew_tasks.append(crew_task)

# Create and execute crew
self.crew = Crew(
    agents=list(set(crew_agents)),
    tasks=crew_tasks,
    process=Process.sequential,
    verbose=True,
)

result = await loop.run_in_executor(None, self.crew.kickoff)
```

---

## Agent Implementation

### Browser Agent

**File**: `src/computer_use/agents/browser_agent.py`

**Architecture**:

```python
class BrowserAgent:
    """
    Web automation specialist using Browser-Use.
    Handles all web-based tasks with high accuracy.
    """

    def __init__(self, tool_registry):
        self.tool_registry = tool_registry
        self.browser_tool = tool_registry.get_tool("browser")

    async def execute_task(
        self, task: str, url: str = None, context: dict = None
    ) -> ActionResult:
        """
        Execute web automation task.

        Args:
            task: Natural language task description
            url: Optional starting URL
            context: Context from previous agents

        Returns:
            ActionResult with status and data
        """
        # Prepend guidelines and context
        enhanced_task = BROWSER_AGENT_GUIDELINES + "\n\n"

        if context and context.get("previous_results"):
            # Add context from previous agents
            enhanced_task += self._format_context(context)

        enhanced_task += f"YOUR TASK: {task}"

    # Execute with Browser-Use
    result = await self.browser_tool.execute_task(enhanced_task, url)
        return result  # Already ActionResult
```

**Key Features**:

- Browser-Use integration with max_steps=30 limit
- max_failures=5 for retry logic
- Automatic file tracking and path resolution
- Phone verification via Twilio
- QR code detection and escalation
- Human help requests for CAPTCHAs

**Loop Prevention**:

```python
agent = Agent(
    task=enhanced_task,
    llm=self.llm_client,
    browser_session=browser_session,
    max_failures=5,      # Allow retries
)

result = await agent.run(max_steps=30)  # Hard limit
```

### GUI Agent

**File**: `src/computer_use/agents/gui_agent.py`

**Screenshot-Driven Architecture**:

```python
class GUIAgent:
    """
    Desktop application control specialist.
    Uses multi-tier accuracy system.
    """

    async def execute_task(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
    """Execute GUI task using screenshot-driven loop."""

    step = 0
    while step < self.max_steps and not task_complete:
        step += 1

        # 1. Capture current screen state
            screenshot = self.screenshot_tool.capture()

        # 2. Get accessibility elements if app is focused
        accessibility_elements = []
        if self.current_app:
                accessibility_elements = self.accessibility_tool.get_all_interactive_elements(
                    app=self.current_app
                )

        # 3. LLM analyzes screenshot and decides next action
        action: GUIAction = await self._analyze_screenshot(
            task, screenshot, step, last_action, accessibility_elements
        )

        # 4. Execute the action
        step_result = await self._execute_action(action, screenshot)

        # 5. Check for loops and failures
        if consecutive_failures >= 2:
            return ActionResult(
                    success=False,
                handoff_requested=True,
                suggested_agent="system",
                    handoff_reason="GUI agent stuck after multiple failures"
            )

        task_complete = action.is_complete

    return ActionResult(success=task_complete, ...)
```

**Multi-Tier Click System**:

```python
async def _click_element(
    self, target: str, screenshot: Image.Image
) -> Dict[str, Any]:
    """Click using tiered approach for maximum accuracy."""

    # TIER 1A: Native accessibility click
    clicked, element = self.accessibility_tool.click_element(
        target, self.current_app
    )
    if clicked:
        return {
            "success": True,
            "method": "accessibility_native",
            "confidence": 1.0
        }

    # TIER 1B: Accessibility coordinates
    if element:
        center = element.get("center")
        if center:
            self.input_tool.click(center[0], center[1])
            return {
                "success": True,
                "method": "accessibility_coordinates",
                "confidence": 1.0
            }

    # TIER 2: OCR with fuzzy matching
    text_matches = self.ocr_tool.find_text(screenshot, target, fuzzy=True)
    if text_matches:
        x, y = text_matches[0]["center"]
        self.input_tool.click(x, y)
        return {
            "success": True,
            "method": "ocr",
            "confidence": text_matches[0]["confidence"]
        }

    # TIER 3: Vision LLM (if enabled)
    # ... vision fallback code

    return {"success": False, "error": f"Could not locate: {target}"}
```

### System Agent

**File**: `src/computer_use/agents/system_agent.py`

**Iterative Command Architecture**:

```python
class SystemAgent:
    """
    Shell-command driven system agent.
    Uses LLM to generate commands iteratively.
    """

    async def execute_task(
        self, task: str, context: Dict[str, Any] = None
    ) -> ActionResult:
        """Execute system task via shell commands."""

        step = 0
        previous_results = []
        last_output = ""

        while step < self.max_steps:
            step += 1

            # LLM generates next command
            command_decision = await self._get_next_command(
                task=task,
                handoff_context=context.get("handoff_context"),
                previous_results=previous_results,
                last_output=last_output,
                step=step
            )

            if command_decision.is_complete:
                break

            # Execute command safely
            cmd_result = self._execute_command(command_decision.command)
            previous_results.append(cmd_result)
            last_output = cmd_result.get("output", "")

            if command_decision.needs_handoff:
                # Hand off to GUI agent
            return ActionResult(
                success=False,
                handoff_requested=True,
                    suggested_agent="gui",
                    handoff_reason=command_decision.handoff_reason
                )

        return ActionResult(success=True, ...)
```

**Structured Command Generation**:

```python
class ShellCommand(BaseModel):
    """Structured command output from LLM."""
    command: str = Field(description="Shell command to execute")
    reasoning: str = Field(description="Why this command")
    is_complete: bool = Field(description="Task complete?")
    needs_handoff: bool = Field(default=False)
    handoff_reason: Optional[str] = None

async def _get_next_command(self, ...) -> ShellCommand:
    """Generate next command using LLM."""
    prompt = f"""
    TASK: {task}
    STEP: {step}
    PREVIOUS RESULTS: {previous_results}

    Generate the next command to make progress.
    """

    structured_llm = self.llm_client.with_structured_output(ShellCommand)
    decision = await structured_llm.ainvoke(prompt)
    return decision
```

---

## Inter-Agent Communication

### CrewAI Context Passing

CrewAI handles context passing automatically:

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
    description="Open Excel and create chart from downloaded data",
    agent=gui_agent,
    expected_output="Excel workbook with chart",
    context=[browser_task],  # ← CrewAI passes browser_task output!
)

# Execute
crew = Crew(
    agents=[browser_agent, gui_agent],
    tasks=[browser_task, gui_task],
    process=Process.sequential,
)
result = crew.kickoff()
```

### Structured Output Format

**TaskCompletionOutput** (Pydantic):

```python
class TaskCompletionOutput(BaseModel):
    """Structured output from agent task completion."""

    success: bool = Field(description="Task completion status")
    result: str = Field(description="Detailed result description")
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

**Browser Agent Output Example**:

```python
TaskCompletionOutput(
    success=True,
    result="Downloaded Tesla stock data from Yahoo Finance",
    files=["/tmp/browser_agent_xyz/tesla_stock.csv"],
    data={
        "stock_symbol": "TSLA",
        "current_price": 195.21,
        "file_size": "15KB"
    },
    next_steps="Data is ready for processing in Excel or other tools"
)
```

### Context Flow Example

**Request**: "Download Nvidia report and create summary in TextEdit"

**Step 1 - Browser Agent**:

```python
# Browser agent executes
output = TaskCompletionOutput(
    success=True,
    result="Downloaded Nvidia quarterly report",
    files=["/tmp/browser_agent_abc/nvidia_q4_2024.pdf"],
    data={"file_size": "2.3MB", "pages": 45}
)
```

**Step 2 - CrewAI Context Passing**:

```
CrewAI automatically adds browser output to GUI task context:

CONTEXT FOR GUI AGENT:
Previous Task Output:
- Success: True
- Result: Downloaded Nvidia quarterly report
- Files: /tmp/browser_agent_abc/nvidia_q4_2024.pdf
- Data: {'file_size': '2.3MB', 'pages': 45}
```

**Step 3 - GUI Agent Execution**:

```python
# GUI agent receives context
# Opens TextEdit
# Creates summary using file path from context
# Returns completion
```

---

## Platform-Specific Implementation

### macOS Implementation

**Accessibility Tool**: `src/computer_use/tools/accessibility/macos_accessibility.py`

```python
class MacOSAccessibility:
    """
    macOS NSAccessibility API wrapper via atomacos.
    Provides 100% accurate element detection.
    """

    def find_elements(
        self,
        app: str,
        role: Optional[str] = None,
        title: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find elements using NSAccessibility.

        Args:
            app: Application name (e.g., "Calculator")
            role: AXRole (e.g., "AXButton", "AXTextField")
            title: AXTitle (element text)

        Returns:
            List of elements with normalized properties:
            [{'center': (x, y), 'role': 'AXButton', 'title': '5', ...}]
        """
        import atomacos

        # Get application
        app_ref = atomacos.getAppRefByBundleId(self._get_bundle_id(app))
        if not app_ref:
            return []

        # Search for elements
        elements = []
        if role:
            found = app_ref.findAll(AXRole=role)
            for element in found:
                if title and element.AXTitle != title:
                    continue

                # Get position and size
                pos = element.AXPosition
                size = element.AXSize
                center_x = int(pos[0] + size[0] / 2)
                center_y = int(pos[1] + size[1] / 2)

                elements.append({
                    'center': (center_x, center_y),
                    'role': element.AXRole,
                    'title': element.AXTitle,
                    'value': element.AXValue,
                    'enabled': element.AXEnabled,
                })

        return elements
```

**Key Features**:

- NSAccessibility API via atomacos
- Bundle ID resolution for apps
- Normalized output format (cross-platform)
- Position calculation from AXPosition + AXSize
- Role, title, value extraction

### Windows Implementation

**Accessibility Tool**: `src/computer_use/tools/accessibility/windows_accessibility.py`

```python
class WindowsAccessibility:
    """
    Windows UI Automation API wrapper via pywinauto.
    Provides 100% accurate element detection.
    """

    def find_elements(
        self,
        app: str,
        control_type: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find elements using UI Automation.

        Args:
            app: Application name (e.g., "Calculator")
            control_type: Control type (e.g., "Button", "Edit")
            name: Control name (element text)

        Returns:
            Normalized element list (same format as macOS)
        """
        from pywinauto import Application

        # Connect to application
        app_ref = Application(backend="uia").connect(title_re=f".*{app}.*")
        window = app_ref.window(title_re=f".*{app}.*")

        # Find elements
        elements = []
        if control_type:
            found = window.descendants(control_type=control_type)
            for element in found:
                if name and element.window_text() != name:
                    continue

                # Get rectangle
                rect = element.rectangle()
                center_x = (rect.left + rect.right) // 2
                center_y = (rect.top + rect.bottom) // 2

                elements.append({
                    'center': (center_x, center_y),
                    'role': element.element_info.control_type,
                    'title': element.window_text(),
                    'enabled': element.is_enabled(),
                })

        return elements
```

**Key Features**:

- UI Automation API via pywinauto
- UIA backend for modern apps
- Window connection via title
- Rectangle-based position calculation
- Normalized output (cross-platform compatible)

### Linux Implementation

**Accessibility Tool**: `src/computer_use/tools/accessibility/linux_accessibility.py`

```python
class LinuxAccessibility:
    """
    Linux AT-SPI protocol wrapper via pyatspi.
    Provides 100% accurate element detection.
    """

    def find_elements(
        self,
        app: str,
        role: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find elements using AT-SPI.

        Args:
            app: Application name (e.g., "gnome-calculator")
            role: Role name (e.g., "push button", "text")
            name: Element name (text)

        Returns:
            Normalized element list
        """
        import pyatspi

        # Get desktop
        desktop = pyatspi.Registry.getDesktop(0)

        # Find application
        app_ref = None
        for child in desktop:
            if app.lower() in child.name.lower():
                app_ref = child
                break

        if not app_ref:
            return []

        # Search recursively
        elements = []
        self._search_elements(app_ref, role, name, elements)
        return elements

    def _search_elements(self, obj, role, name, results):
        """Recursively search AT-SPI tree."""
        try:
            # Check if matches
            if role and obj.get_role_name() == role:
                if not name or obj.name == name:
                    # Get component interface for position
                    component = obj.queryComponent()
                    extents = component.getExtents(pyatspi.DESKTOP_COORDS)

                    center_x = extents.x + extents.width // 2
                    center_y = extents.y + extents.height // 2

                    results.append({
                        'center': (center_x, center_y),
                        'role': obj.get_role_name(),
                        'title': obj.name,
                        'enabled': obj.get_state().contains(pyatspi.STATE_ENABLED),
                    })

            # Recurse to children
            for i in range(obj.child_count):
                child = obj.get_child_at_index(i)
                self._search_elements(child, role, name, results)
        except Exception:
            pass
```

**Key Features**:

- AT-SPI protocol via pyatspi
- Desktop registry access
- Recursive element tree search
- Component interface for coordinates
- Normalized output format

---

## Multi-Tier Accuracy System

### Tier 1: Platform APIs (100% Accuracy)

**Detection Flow**:

```python
def detect_element_tier1(app: str, target: str) -> Optional[Tuple[int, int]]:
    """
    Tier 1: Use platform accessibility API.

    Returns:
        (x, y) coordinates or None
    """
    # Detect platform
    platform = detect_platform()

    if platform.os_type == "macos":
        accessor = MacOSAccessibility()
    elif platform.os_type == "windows":
        accessor = WindowsAccessibility()
    elif platform.os_type == "linux":
        accessor = LinuxAccessibility()
    else:
        return None

    # Search for element
    elements = accessor.find_elements(app=app, title=target)
    if elements:
        return elements[0]['center']  # 100% accurate coordinates

    return None
```

### Tier 2: OCR + CV (95-99% Accuracy)

**Engine Selection**:

```python
class OCRTool:
    """
    Multi-engine OCR with automatic fallback.
    """

    def __init__(self, engine: str = "auto"):
        """
        Initialize OCR tool.

        Args:
            engine: "easyocr", "paddleocr", "macos_vision", or "auto"
        """
        if engine == "auto":
            # Auto-select best engine for platform
            if sys.platform == "darwin":
                engine = "macos_vision"
            else:
                engine = "easyocr"

        self.engine = engine
        self._init_engine()

    def find_text(
        self,
        screenshot: Image.Image,
        target: str,
        fuzzy: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find text in screenshot using OCR.

        Args:
            screenshot: PIL Image
            target: Text to find
            fuzzy: Allow fuzzy matching

        Returns:
            [{'text': str, 'confidence': float, 'center': (x, y)}]
        """
        # Run OCR
        if self.engine == "easyocr":
            results = self._easyocr_detect(screenshot)
        elif self.engine == "paddleocr":
            results = self._paddleocr_detect(screenshot)
        elif self.engine == "macos_vision":
            results = self._macos_vision_detect(screenshot)

        # Filter and match
        matches = []
        for result in results:
            text = result['text']
            if fuzzy:
                similarity = self._fuzzy_match(text, target)
                if similarity > 0.85:
                    matches.append({
                        'text': text,
                        'confidence': result['confidence'] * similarity,
                        'center': result['center']
                    })
            elif text == target:
                matches.append(result)

        return sorted(matches, key=lambda x: x['confidence'], reverse=True)
```

**OpenCV Template Matching**:

```python
class TemplateMatcher:
    """
    OpenCV-based template matching for icons/buttons.
    """

    def find_template(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.8
    ) -> Optional[Dict[str, Any]]:
        """
        Find template in screenshot.

        Args:
            screenshot: Screenshot as numpy array
            template: Template image as numpy array
            threshold: Confidence threshold (0.0-1.0)

        Returns:
            {'center': (x, y), 'confidence': float} or None
        """
        import cv2

        # Convert to grayscale
        gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        # Template matching
        result = cv2.matchTemplate(
            gray_screen,
            gray_template,
            cv2.TM_CCOEFF_NORMED
        )

        # Get best match
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            # Calculate center
            h, w = gray_template.shape
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2

            return {
                'center': (center_x, center_y),
                'confidence': float(max_val)
            }

        return None
```

### Tier 3: Vision LLMs (85-95% Accuracy)

**Implementation**:

```python
class VisionCoordinates:
    """
    Vision LLM fallback for element detection.
    """

    def __init__(self, llm: BaseChatModel):
        """
        Initialize with vision-capable LLM.

        Args:
            llm: LangChain vision LLM (GPT-4V, Claude, Gemini)
        """
        self.llm = llm

    async def find_element(
        self,
        screenshot: Image.Image,
        target: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find element using vision LLM.

        Args:
            screenshot: PIL Image
            target: Description of element to find

        Returns:
            {'x': int, 'y': int, 'confidence': float} or None
        """
        # Convert screenshot to base64
        buffered = BytesIO()
        screenshot.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        # Create vision prompt
        prompt = f"""
        Analyze this screenshot and locate the element: "{target}"

        Provide the center coordinates (x, y) where this element is located.
        Image dimensions: {screenshot.width}x{screenshot.height}

        Return JSON:
        {{
            "x": <x coordinate>,
            "y": <y coordinate>,
            "confidence": <0.0-1.0>
        }}
        """

        # Invoke vision LLM
        from langchain_core.messages import HumanMessage

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": f"data:image/png;base64,{img_str}"}
            ]
        )

        response = await self.llm.ainvoke([message])

        # Parse JSON response
        try:
            data = json.loads(response.content)
            return data
        except json.JSONDecodeError:
            return None
```

---

## CrewAI Tools

### Tool Structure

All tools inherit from CrewAI's `BaseTool`:

```python
from crewai.tools import BaseTool
from pydantic import Field

class ExampleTool(BaseTool):
    """Example CrewAI tool."""

    name: str = "example_tool"
    description: str = "Description of what this tool does"

    # Dependencies (injected by crew.py)
    _tool_registry: Any = None
    _llm: Any = None

    def _run(self, param1: str, param2: int = 5) -> str:
        """
        Execute tool synchronously.

        Args:
            param1: Description
            param2: Description with default

        Returns:
            Result string
        """
        # Tool implementation
        return f"Result: {param1}, {param2}"
```

### GUI Tools (13 tools)

Defined in `src/computer_use/crew_tools/`:

- `gui_basic_tools.py`: Screenshot, Open App, Read Text, Scroll
- `gui_interaction_tools.py`: Click, Type, Get Elements, Get Image
- `capability_tools.py`: Find Application, Request Human Input

**Example**: ClickElementTool

```python
class ClickElementTool(BaseTool):
    """Click UI element with multi-tier accuracy."""

    name: str = "click_element"
    description: str = """
    Click a UI element by name/description.
    Uses multi-tier detection (accessibility → OCR → vision).
    """

    _tool_registry: Any = None

    def _run(
        self,
        target: str,
        element: dict = None,
        visual_context: str = None,
        current_app: str = None
    ) -> str:
        """Click element using best available method."""
        input_tool = self._tool_registry.get_tool("input")
        accessibility_tool = self._tool_registry.get_tool("accessibility")

        # Tier 1: Use provided element (from get_accessible_elements)
        if element and "center" in element:
            x, y = element["center"]
            input_tool.click(x, y)
            return f"✅ Clicked {target} at ({x}, {y}) via accessibility"

        # Tier 1B: Search accessibility
        if current_app:
            elements = accessibility_tool.find_elements(
                app=current_app,
                title=target
            )
            if elements:
                x, y = elements[0]["center"]
                input_tool.click(x, y)
                return f"✅ Clicked {target} via accessibility search"

        # Tier 2: OCR (implementation continues...)
        # ...
```

### Web Tools (1 tool)

**WebAutomationTool** (`web_tools.py`):

```python
class WebAutomationTool(BaseTool):
    """Execute web automation via Browser-Use."""

    name: str = "web_automation"
    description: str = """
    Automate web browser tasks using Browser-Use.
    Handles navigation, clicking, typing, downloads, phone verification.
    """

    _tool_registry: Any = None

    def _run(self, task: str, url: str = None) -> str:
        """
        Execute browser automation task.

        Args:
            task: Detailed task description
            url: Optional starting URL

        Returns:
            Formatted result with file paths
        """
        browser_tool = self._tool_registry.get_tool("browser")

        # Execute browser automation (async wrapper)
        import asyncio
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            browser_tool.execute_task(task, url)
        )

        # Format output
        if result.success and result.data:
            output = result.data.get("output", {})
            if isinstance(output, dict):
                from schemas.browser_output import BrowserOutput
                browser_output = BrowserOutput(**output)
                return browser_output.format_summary()

        return str(result)
```

### System Tools (1 tool)

**ExecuteShellCommandTool** (`system_tools.py`):

```python
class ExecuteShellCommandTool(BaseTool):
    """Execute shell commands safely."""

    name: str = "execute_shell_command"
    description: str = """
    Execute terminal/shell commands safely.
    Validates commands before execution.
    """

    _safety_checker: Any = None
    _confirmation_manager: Any = None

    def _run(self, command: str) -> str:
        """
        Execute shell command with safety checks.

        Args:
            command: Shell command to execute

        Returns:
            Command output or error
        """
        # Safety validation
        if self._safety_checker.is_destructive(command):
            # Request user confirmation
            if not self._confirmation_manager.confirm(command):
                return "❌ Command rejected by user"

        # Execute
        import subprocess
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return f"✅ SUCCESS\n{result.stdout}"
            else:
                return f"❌ ERROR (exit code {result.returncode})\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return "❌ Command timed out after 30 seconds"
        except Exception as e:
            return f"❌ Execution error: {str(e)}"
```

---

## Type Safety & Schemas

### ActionResult Schema

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ActionResult(BaseModel):
    """
    Unified result type for all agent executions.
    Ensures type safety and structured data flow.
    """

    success: bool = Field(description="Whether action succeeded")
    action_taken: str = Field(description="What was done")
    method_used: str = Field(description="Which method/agent was used")
    confidence: float = Field(description="Confidence level (0.0-1.0)")

    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional structured data (output, files, etc.)"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )

    # Handoff fields (legacy, not used in CrewAI version)
    handoff_requested: bool = Field(
        default=False,
        description="Whether agent requests handoff"
    )
    suggested_agent: Optional[str] = Field(
        default=None,
        description="Which agent to hand off to"
    )
    handoff_reason: Optional[str] = Field(
        default=None,
        description="Why handoff is needed"
    )
```

### BrowserOutput Schema

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class FileDetail(BaseModel):
    """Metadata for a downloaded file."""
    path: str = Field(description="Absolute file path")
    name: str = Field(description="Filename")
    size: int = Field(description="Size in bytes")

class BrowserOutput(BaseModel):
    """Structured output from Browser agent."""

    text: str = Field(description="Summary of actions and findings")
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

    def has_files(self) -> bool:
        """Check if files are present."""
        return len(self.files) > 0

    def get_file_count(self) -> int:
        """Get number of files."""
        return len(self.files)

    def format_summary(self) -> str:
        """Format comprehensive summary with file info."""
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

---

## Configuration

### LLM Configuration

**File**: `src/computer_use/config/llm_config.py`

```python
class LLMConfig:
    """
    LLM configuration for all agents.
    Supports OpenAI, Anthropic, Google, Ollama.
    """

    @staticmethod
    def get_llm(provider: Optional[str] = None, model: Optional[str] = None):
        """
        Get CrewAI LLM (uses LiteLLM internally).

        Returns:
            CrewAI LLM instance
        """
        from crewai import LLM

        provider = provider or os.getenv("LLM_PROVIDER", "google")
        model_name = model or os.getenv("LLM_MODEL", "gemini-2.0-flash-exp")

        # Format for LiteLLM
        if provider == "google" and not model_name.startswith("gemini/"):
            model_name = f"gemini/{model_name}"

        # Get API key
        api_key = os.getenv(f"{provider.upper()}_API_KEY")

        return LLM(model=model_name, temperature=0, api_key=api_key)

    @staticmethod
    def get_orchestration_llm(provider: Optional[str] = None, model: Optional[str] = None):
        """
        Get LangChain LLM for task decomposition.
        Supports structured output.

        Returns:
            LangChain BaseChatModel
        """
        provider = provider or os.getenv("ORCHESTRATION_LLM_PROVIDER", "google")
        model_name = model or os.getenv("ORCHESTRATION_LLM_MODEL", "gemini-2.0-flash-exp")

        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_name,
                api_key=os.getenv("GOOGLE_API_KEY")
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_name,
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_name,
                api_key=os.getenv("OPENAI_API_KEY")
            )
```

### Agent Configuration

**File**: `src/computer_use/config/agents.yaml`

Defines all agent roles, goals, and tool assignments:

```yaml
manager:
  role: Task Orchestration Manager
  goal: Coordinate specialist agents efficiently
  backstory: |
    You coordinate specialized automation agents.
    Delegate tasks to appropriate specialists.
  allow_delegation: true
  verbose: true

browser_agent:
  role: Web Automation Specialist
  goal: Navigate websites, download files, fill forms
  tools:
    - web_automation
  max_iter: 20
  verbose: true

gui_agent:
  role: Desktop Application Automation Expert
  goal: Automate any desktop application
  tools:
    - open_application
    - get_accessible_elements
    - click_element
    - type_text
    - read_screen_text
    # ... more tools
  max_iter: 25
  verbose: true

system_agent:
  role: System Command & Terminal Expert
  goal: Execute commands and file operations safely
  tools:
    - execute_shell_command
  max_iter: 10
  verbose: true
```

---

## Development Standards

### Code Quality Rules

1. **File Size**: Maximum 400 lines per file
2. **Documentation**: Only docstrings (NO inline comments)
3. **Type Hints**: Always use type hints
4. **Modularity**: Zero redundancy (DRY principle)
5. **Error Handling**: Comprehensive with meaningful messages

### Python Standards

- Follow PEP 8
- Use type hints for all functions
- List/dict comprehensions when appropriate
- Proper exception handling
- Meaningful variable and function names
- Maximum 3-4 levels of nesting

### Testing Standards

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=computer_use

# Run linting
uv run ruff check .
uv run ruff format .
```

### Folder Organization

```
src/computer_use/
├── agents/              # Agent implementations
├── tools/               # Low-level tool implementations
├── crew_tools/          # CrewAI tool wrappers
├── schemas/             # Pydantic models
├── config/              # Configuration files
├── utils/               # Utility modules
├── services/            # External services (Twilio)
├── prompts/             # Prompt templates
└── main.py              # Entry point
```

---

**End of Technical Reference**

_This document reflects the current CrewAI-based architecture as of January 2025._
