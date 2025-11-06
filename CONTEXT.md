# Computer Use Agent - Complete Technical Reference

> **Last Updated**: November 6, 2025  
> **Purpose**: Comprehensive technical reference for architecture, implementation, and development patterns

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Type Safety & Schemas](#type-safety--schemas)
4. [Agent Implementation](#agent-implementation)
5. [Inter-Agent Communication](#inter-agent-communication)
6. [Browser-Use Integration](#browser-use-integration)
7. [Recent Improvements](#recent-improvements)
8. [File Structure](#file-structure)
9. [Configuration](#configuration)
10. [Development Standards](#development-standards)
11. [Key Design Decisions](#key-design-decisions)

---

## Project Overview

### Purpose

A multi-agent autonomous desktop and web automation system that combines:

- **Browser automation** for web tasks (downloads, forms, research)
- **GUI automation** for desktop applications (visual control)
- **System automation** for terminal commands and file operations
- **Intelligent coordination** to route tasks to specialized agents

### Core Technology Stack

- **Framework**: CrewAI for agent orchestration
- **Browser Automation**: Browser-Use (v0.8.1+)
- **GUI Automation**:
  - macOS: NSAccessibility API (100% accuracy)
  - Windows: pywinauto
  - Linux: AT-SPI (pyatspi)
- **Vision**:
  - EasyOCR for text recognition
  - OpenCV for element detection
  - Vision LLMs (Gemini, Claude, GPT-4V) for screenshot analysis
- **Type Safety**: Pydantic for schemas and validation
- **UI**: Rich library for professional terminal interface
- **LLM Providers**: Google Gemini, Anthropic Claude, OpenAI GPT
- **Phone Verification**: Twilio for SMS verification automation

### Platform Support

- **macOS**: Full support (primary platform)
- **Windows**: Full support
- **Linux**: Full support

---

## Architecture

### Agent Hierarchy

```
Coordinator Agent (Task analysis & routing)
    ├── Browser Agent (Web automation specialist)
    ├── GUI Agent (Desktop application control)
    └── System Agent (Terminal commands)
```

### Multi-Tier Accuracy System

**GUI Agent uses 3-tier fallback for maximum reliability:**

1. **Tier 1**: Accessibility API (100% accuracy)

   - Native element identification via OS APIs
   - Precise coordinates without vision
   - Instant, deterministic results

2. **Tier 2**: Computer Vision + OCR (95-99% accuracy)

   - EasyOCR for text recognition
   - OpenCV for element detection
   - Fuzzy matching for robustness

3. **Tier 3**: Vision LLM (85-95% accuracy)
   - Screenshot analysis via vision models
   - Semantic understanding
   - Fallback when text not visible

### Data Flow

```
User Task
    ↓
Coordinator analyzes with LLM
    ↓
Sequential agent execution
    ↓
Type-safe ActionResult from each agent
    ↓
Context passed between agents (serialized)
    ↓
Results aggregated (typed)
    ↓
Final summary (serialized)
```

---

## Type Safety & Schemas

### Why Pydantic?

1. **Compile-Time Safety**: IDE catches errors before runtime
2. **Automatic Validation**: Invalid data rejected immediately
3. **Self-Documenting**: Schema is documentation
4. **Easy Serialization**: `.model_dump()` and `.model_validate()`
5. **IDE Support**: Full autocomplete for all fields

### ActionResult Schema

**All agents return this unified type:**

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ActionResult(BaseModel):
    """Unified result type for all agents."""

    success: bool = Field(description="Whether action succeeded")
    action_taken: str = Field(description="What was done")
    method_used: str = Field(description="Which method/agent was used")
    confidence: float = Field(description="Confidence level (0.0-1.0)")

    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional data (output, files, etc.)"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )

    # Handoff fields
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
    handoff_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Context for handoff agent"
    )
```

### BrowserOutput Schema

**Browser-specific structured output:**

```python
class FileDetail(BaseModel):
    """Metadata for a single file."""
    path: str = Field(description="Absolute path to file")
    name: str = Field(description="Filename")
    size: int = Field(description="Size in bytes")

class BrowserOutput(BaseModel):
    """Structured output from Browser agent."""

    text: str = Field(
        description="Summary of actions and findings"
    )
    files: List[str] = Field(
        default_factory=list,
        description="Absolute paths to relevant files"
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

    def get_total_size_kb(self) -> float:
        """Get total size of all files in KB."""
        return sum(f.size for f in self.file_details) / 1024

    def format_summary(self) -> str:
        """Format comprehensive summary with files."""
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

### Usage Pattern

```python
# Agent returns typed result
result: ActionResult = await browser_agent.execute_task(task)

# Type-safe access with IDE autocomplete
if result.success:
    output_dict = result.data.get("output", {})
    browser_output = BrowserOutput(**output_dict)

    # All fields typed and validated
    print(browser_output.text)
    for file_detail in browser_output.file_details:
        print(f"{file_detail.name}: {file_detail.size} bytes")
```

### Benefits

- **No Runtime Errors**: Typos caught at development time
- **Self-Documenting**: Schema shows all available fields
- **IDE Support**: Full autocomplete and type checking
- **Refactoring Safety**: Changes propagate automatically
- **Validation**: Pydantic ensures data consistency

---

## Agent Implementation

### Browser Agent

**File**: `src/computer_use/agents/browser_agent.py`

**Responsibilities**:

- Web navigation and interaction
- File downloads
- Form filling and submission
- Phone verification with SMS codes (via Twilio)
- Data extraction from websites
- API calls through browser

**Principle-Based Guidelines**:

The agent understands its role through generic principles:

```python
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
```

**Implementation**:

```python
async def execute_task(self, task: str, url: str = None, context: dict = None) -> ActionResult:
    """Execute web automation task."""

    # Prepend principles to task
    enhanced_task = handoff_guidelines + "\n\n" + f"YOUR TASK: {task}"

    # Execute with Browser-Use
    result = await self.browser_tool.execute_task(enhanced_task, url)

    return result  # Already ActionResult (typed)
```

**Loop Prevention**:

- Max 30 steps per task
- Max 5 failures allowed for retries
- Smart done() detection based on principles

### GUI Agent

**File**: `src/computer_use/agents/gui_agent.py`

**Responsibilities**:

- Desktop application control
- Screenshot-driven automation
- Mouse and keyboard actions
- Context menu operations
- File operations (copy, paste, open)

**Screenshot-Driven Loop**:

```python
async def execute_task(self, task: str, context: Optional[Dict[str, Any]] = None) -> ActionResult:
    """Execute GUI task using screenshot-driven loop."""

    step = 0
    while step < self.max_steps and not task_complete:
        step += 1

        # 1. Capture current screen state
        screenshot = screenshot_tool.capture()

        # 2. Get accessibility elements if app is focused
        accessibility_elements = []
        if self.current_app:
            accessibility_elements = accessibility_tool.get_all_interactive_elements(app)

        # 3. LLM analyzes screenshot and decides next action
        action: GUIAction = await self._analyze_screenshot(
            task, screenshot, step, last_action, accessibility_elements
        )

        # 4. Execute the action
        step_result = await self._execute_action(action, screenshot)

        # 5. Check for loops and failures
        if consecutive_failures >= 2:
            return ActionResult(
                handoff_requested=True,
                suggested_agent="system",
                ...
            )

        task_complete = action.is_complete

    return ActionResult(success=task_complete, ...)
```

**Multi-Tier Click System**:

```python
async def _click_element(self, target: str, screenshot: Image.Image) -> Dict[str, Any]:
    """Click using tiered approach for maximum accuracy."""

    # TIER 1A: Native accessibility click
    clicked, element = accessibility_tool.click_element(target, self.current_app)
    if clicked:
        return {"success": True, "method": "accessibility_native", "confidence": 1.0}

    # TIER 1B: Accessibility coordinates
    if element:
        pos = element.AXPosition
        size = element.AXSize
        x, y = int(pos[0] + size[0]/2), int(pos[1] + size[1]/2)
        input_tool.click(x, y)
        return {"success": True, "method": "accessibility_coordinates", "confidence": 1.0}

    # TIER 2: OCR with fuzzy matching
    text_matches = ocr_tool.find_text(screenshot, target, fuzzy=True)
    if text_matches:
        x, y = text_matches[0]["center"]
        input_tool.click(x, y)
        return {"success": True, "method": "ocr", "confidence": text_matches[0]["confidence"]}

    return {"success": False, "error": f"Could not locate: {target}"}
```

**Loop Detection**:

```python
# Detect back-and-forth patterns
if len(self.action_history) >= 4:
    recent_targets = [h["target"] for h in action_history[-4:]]

    if len(set(recent_targets)) == 2:  # Only 2 unique targets
        is_alternating = all(
            targets[i] != targets[i+1] for i in range(len(targets)-1)
        )
        if is_alternating:  # A→B→A→B pattern
            return ActionResult(
                success=False,
                handoff_requested=True,
                suggested_agent="system",
                handoff_reason=f"GUI stuck in loop: {targets[0]} ↔ {targets[1]}"
            )
```

### System Agent

**File**: `src/computer_use/agents/system_agent.py`

**Responsibilities**:

- Terminal command execution
- File system operations
- Process management
- System-level tasks

**Safety Features**:

- Command approval dialog for dangerous operations
- Sandboxed execution
- Git operation protection
- No force push to main/master
- Hook preservation (no --no-verify)

---

## Inter-Agent Communication

### Context Passing Strategy

**Principle**: Keep types as long as possible, serialize only at boundaries.

```python
# 1. Agent execution returns typed result
result: ActionResult = await self._execute_browser(task, context)

# 2. Store internally as typed object
results.append(result)  # List[ActionResult]

# 3. Serialize for context passing
context["previous_results"].append(result.model_dump())

# 4. Next agent parses back to typed objects
for res in context.get("previous_results", []):
    output = res.get("data", {}).get("output")
    if isinstance(output, dict):
        browser_output = BrowserOutput(**output)
        # Now fully typed!

# 5. Final serialization at the very end
return {
    "results": [r.model_dump() for r in results],
    "overall_success": all(r.success for r in results)
}
```

### Crew Orchestrator

**File**: `src/computer_use/crew.py`

**Type-Safe Execution**:

```python
async def _execute_browser(self, task: str, context: dict) -> ActionResult:
    """Execute browser agent."""
    return await self.browser_agent.execute_task(task, context=context)

async def _execute_gui(self, task: str, context: dict) -> ActionResult:
    """Execute GUI agent."""
    return await self.gui_agent.execute_task(task, context=context)

async def _execute_system(self, task: str, context: dict) -> ActionResult:
    """Execute system agent."""
    return await self.system_agent.execute_task(task, context)
```

**Type-Safe Handoffs**:

```python
# All field access is typed
if result.success:
    print_success("Task completed successfully")
elif result.handoff_requested:
    suggested = result.suggested_agent
    print_handoff("GUI", suggested.upper() if suggested else "UNKNOWN", result.handoff_reason)

    # Execute handoff
    if suggested == "system":
        handoff_result = await self._execute_system(task, context)

        if handoff_result.success:
            print_success("System agent completed handoff")
        else:
            print_failure(f"System agent failed: {handoff_result.error}")
```

**Smart Browser Handoff Detection**:

```python
# Check if browser finished its attempt
browser_completed_attempt = (
    result.data.get("task_complete", False) if result.data else False
)

if result.success:
    # Full success
    if browser_completed_attempt and not (analysis.requires_gui or analysis.requires_system):
        return self._build_result(task, analysis, results, True)

elif browser_completed_attempt:
    # Partial success - browser did what it could, hand off
    if result.data and "output" in result.data:
        browser_output = BrowserOutput(**result.data["output"])
        print_info(f"Browser says: {browser_output.text}")

        if browser_output.has_files():
            print_info(f"Files available: {browser_output.get_file_count()} file(s)")
    # Continue to next agent
```

### GUI Agent Context Display

The GUI agent receives rich, formatted context:

```
============================================================
PREVIOUS AGENT WORK (Build on this!):
============================================================

✅ Agent 1 (browser): Downloaded data from census.gov

📝 Summary:
Downloaded demographic data from census.gov

📁 DOWNLOADED FILES (use these paths!):
   • /tmp/browser_agent_abc/demographics_2024.csv

📊 File Details:
   • demographics_2024.csv (512.0 KB)
     Path: /tmp/browser_agent_abc/demographics_2024.csv

============================================================
🎯 YOUR JOB: Use the files/data above to complete the current task!
============================================================
```

---

## Browser-Use Integration

### Configuration

```python
from browser_use import Agent, BrowserSession, BrowserProfile

# Create session
browser_session = BrowserSession(browser_profile=BrowserProfile())

# Create agent with limits
agent = Agent(
    task=full_task,
    llm=self.llm_client,
    browser_session=browser_session,
    max_failures=5,  # Retry limit
)

# Run with step limit
result: AgentHistoryList = await agent.run(max_steps=30)

# Cleanup
await browser_session.kill()
```

### Typed API Usage

```python
from browser_use.agent.views import AgentHistoryList

result: AgentHistoryList = await agent.run(max_steps=30)

# Clean typed interface
agent_called_done = result.is_done()
task_completed_successfully = result.is_successful()
final_output = result.final_result()
error_list = result.errors()
```

### File Tracking

```python
downloaded_files = []
file_details = []

# Check attachments
if result.history and len(result.history) > 0:
    attachments = result.history[-1].result[-1].attachments
    if attachments:
        for attachment in attachments:
            attachment_path = Path(attachment)
            if attachment_path.exists():
                downloaded_files.append(str(attachment_path.absolute()))
                file_details.append(FileDetail(
                    path=str(attachment_path.absolute()),
                    name=attachment_path.name,
                    size=attachment_path.stat().st_size
                ))

# Scan working directory
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

# Package into BrowserOutput
browser_output = BrowserOutput(
    text=final_output or "Task completed",
    files=downloaded_files,
    file_details=file_details,
    work_directory=str(temp_dir)
)
```

---

## Recent Improvements

### 1. Credential Hallucination Prevention (Nov 2025)

**Problem**: Browser agent sometimes used test data like `test@gmail.com` instead of actual user-provided credentials.

**Solution**: Added explicit anti-hallucination rules at the top of every browser task:

```python
🚨 CRITICAL RULE #1: USE ONLY PROVIDED CREDENTIALS

✅ Extract EXACT credentials from task
✅ Use tools if credentials not provided
❌ NEVER use test@gmail.com or placeholder data
```

**Impact**: Eliminated authentication failures from credential substitution.

### 2. QR Code Detection & Escalation (Nov 2025)

**Problem**: Agents attempted to automate QR code authentication (impossible).

**Solution**: Immediate human escalation when QR codes detected:

- Detect: Square patterns, "Scan QR code" text, 2FA QR options
- Action: Call `request_human_help()` immediately with clear instructions
- Never attempt to "read" or "process" QR codes

**Impact**: Clean handoff for physical authentication requirements.

### 3. Systematic Escalation Protocol (Nov 2025)

**Problem**: Agents got stuck after repeated failures without asking for help.

**Solution**: Two-tier escalation protocol:

- **Immediate Escalation**: QR codes, visual CAPTCHAs, biometrics
- **After Attempts**: 3+ failures, unexpected page structure, ambiguous choices

**Requirements**:

- Try 2-3 approaches before escalating
- Explain what was tried and why it failed
- Provide specific instructions for user
- Describe current state clearly

**Impact**: Better stuck detection and graceful user escalation.

### 4. Conversation Context & Memory (Nov 2025)

**Problem**: No memory of previous interactions - couldn't answer "What did you just do?".

**Solution**: Rolling 10-interaction conversation history:

```python
conversation_history = []  # Last 10 user interactions

result = await crew.execute_task(task, conversation_history)
conversation_history.append({"user": task, "result": result})
```

**Features**:

- Coordinator analyzes conversation history for context
- Direct responses for conversational queries (no agent execution)
- Context-aware follow-up handling

**Impact**: Natural conversation flow, reduced unnecessary agent executions.

### 5. Enhanced Terminal UI (Nov 2025)

**Problem**: No multi-line input, poor editing experience, visual issues.

**Solution**: Upgraded to `prompt_toolkit` with full features:

- **Alt+Enter** / **Ctrl+J**: Insert newline for multi-line tasks
- **Enter**: Submit task
- **Full line editing**: Arrow keys, backspace, home/end, history
- **Professional styling**: Clean borders, clear instructions, emoji support

**Impact**: Better UX for complex multi-line instructions.

### 6. Twilio Integration Independence (Nov 2025)

**Problem**: Twilio webhook initialization tied to browser agent startup.

**Solution**: Independent initialization at app startup:

```python
# Initialize independently
twilio_service = TwilioService()
webhook_server = WebhookServer(twilio_service)
webhook_server.start()

# Pass to crew
crew = ComputerUseCrew(..., twilio_service=twilio_service)
```

**Impact**: Cleaner architecture, webhook ready before any agent runs.

### 7. Phone Verification Intelligence (Nov 2025)

**Enhancement**: Clear decision flow for phone number sources:

1. Check if phone provided in task prompt
2. If YES → Extract and use exact number
3. If NO → Call `get_verification_phone_number()` tool
4. Parse format based on form structure
5. Get verification code via `get_verification_code()` tool

**Impact**: Flexible phone verification across different scenarios.

---

## File Structure

```
src/computer_use/
├── agents/
│   ├── browser_agent.py      # Web automation
│   ├── gui_agent.py          # Desktop GUI control
│   ├── system_agent.py       # Terminal commands
│   └── coordinator.py        # Task routing
├── tools/
│   ├── browser_tool.py       # Browser-Use wrapper
│   ├── twilio_tools.py       # Twilio custom actions
│   ├── platform_registry.py  # Cross-platform tools
│   ├── accessibility/
│   │   ├── macos_accessibility.py
│   │   ├── windows_accessibility.py
│   │   └── linux_accessibility.py
│   ├── vision/
│   │   ├── ocr_tool.py       # EasyOCR
│   │   └── cv_tool.py        # OpenCV
│   ├── input_tool.py         # Mouse/keyboard
│   ├── screenshot_tool.py    # Screen capture
│   ├── process_tool.py       # App launching
│   └── file_tool.py          # File operations
├── services/
│   ├── twilio_service.py     # SMS management
│   └── webhook_server.py     # SMS webhook receiver
├── schemas/
│   ├── actions.py            # ActionResult
│   └── browser_output.py     # BrowserOutput, FileDetail
├── config/
│   ├── llm_config.py         # LLM setup
│   ├── agents.yaml           # Agent definitions
│   └── tasks.yaml            # Task definitions
├── utils/
│   ├── ui.py                 # Rich terminal UI
│   ├── command_confirmation.py  # Safety dialogs
│   ├── permissions.py        # Permission checking
│   └── logging_config.py     # Log configuration
├── main.py                   # Entry point
└── crew.py                   # Orchestration
```

---

## Configuration

### Environment Variables

`.env` file:

```bash
# Primary LLM (GUI/System agents)
LLM_PROVIDER=google
LLM_MODEL=gemini-2.0-flash-exp

# Browser agent LLM
BROWSER_LLM_PROVIDER=google
BROWSER_LLM_MODEL=gemini-2.5-flash

# API Keys
GOOGLE_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key

# Twilio (Optional - for phone verification)
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1234567890
```

### LLM Configuration

**File**: `src/computer_use/config/llm_config.py`

```python
class LLMConfig:
    @staticmethod
    def get_vision_llm() -> BaseChatModel:
        """Get vision LLM for GUI agent."""
        provider = os.getenv("LLM_PROVIDER", "google")

        if provider == "google":
            return ChatGoogleGenerativeAI(
                model=os.getenv("LLM_MODEL", "gemini-2.0-flash-exp"),
                api_key=os.getenv("GOOGLE_API_KEY")
            )
        elif provider == "anthropic":
            return ChatAnthropic(
                model=os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"),
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        # ... other providers

    @staticmethod
    def get_browser_llm() -> BaseChatModel:
        """Get LLM for Browser-Use agent."""
        from browser_use.llm.google.chat import ChatGoogle

        provider = os.getenv("BROWSER_LLM_PROVIDER", "google")

        if provider == "google":
            return ChatGoogle(
                model=os.getenv("BROWSER_LLM_MODEL", "gemini-2.5-flash"),
                api_key=os.getenv("GOOGLE_API_KEY")
            )
        # ... other providers
```

**Key Decisions**:

- Separate LLM for browser (Browser-Use needs specific format)
- Explicit API key passing (reliable across platforms)
- Centralized configuration (DRY principle)

### Logging

**File**: `src/computer_use/utils/logging_config.py`

```python
def setup_logging():
    """Suppress verbose third-party logs."""

    # Google gRPC
    os.environ["GRPC_VERBOSITY"] = "ERROR"
    os.environ["GLOG_minloglevel"] = "2"

    # Python logging
    logging.getLogger("google.genai").setLevel(logging.ERROR)
    logging.getLogger("google.auth").setLevel(logging.ERROR)
    logging.getLogger("grpc").setLevel(logging.ERROR)
```

---

## Development Standards

### Code Quality Rules

1. **File Size**: Max 400 lines per file
2. **Documentation**: Only docstrings (NO inline comments)
3. **Type Hints**: Always use type hints
4. **Modular**: Zero redundancy (DRY)
5. **Error Handling**: Comprehensive with meaningful messages

### Python Standards

- Follow PEP 8
- Use type hints for all functions
- List/dict comprehensions when appropriate
- Proper exception handling
- Meaningful names
- Max 3-4 levels of nesting

### Folder Organization

```
src/
├── agents/       # Agent implementations
├── tools/        # Tool implementations
├── schemas/      # Pydantic models
├── config/       # Configuration
├── utils/        # Utilities
└── tests/        # Tests
```

---

## Key Design Decisions

### 1. Type Safety First

**Decision**: Use Pydantic for all inter-agent communication.

**Rationale**:

- Compile-time error detection
- Self-documenting code
- IDE support
- Automatic validation

**Impact**: Zero runtime errors from typos, 10x better developer experience.

### 2. Principle-Based Over Rule-Based

**Decision**: Give agents generic principles, not specific rules.

**Rationale**:

- Scales to any task
- Agents reason about boundaries
- No hardcoded task detection

**Impact**: Browser agent now handles any task intelligently.

### 3. Strategic Serialization

**Decision**: Keep types as long as possible, serialize at boundaries.

**Rationale**:

- Maximum type safety internally
- Clean serialization for external communication
- Performance (no repeated conversions)

**Impact**: Type-safe throughout 95% of codebase.

### 4. Multi-Tier Accuracy

**Decision**: Accessibility first, OCR as fallback, vision as last resort.

**Rationale**:

- 100% accuracy when possible
- Graceful degradation
- Works on any platform

**Impact**: Reliability without sacrificing flexibility.

### 5. Hard Limits

**Decision**: Max 30 steps for browser agent.

**Rationale**:

- Prevents infinite loops
- Protects user's budget
- Forces smart done() calls

**Impact**: 5-6x cost reduction on complex tasks.

---

## Common Patterns

### Agent Return Pattern

```python
async def execute_task(self, task: str, context: dict = None) -> ActionResult:
    """Execute task, always return ActionResult."""
    try:
        # Do work
        result = await self.tool.execute(task)

        return ActionResult(
            success=True,
            action_taken=f"Completed: {task}",
            method_used="agent_name",
            confidence=1.0,
            data={"result": result}
        )
    except Exception as e:
        return ActionResult(
            success=False,
            action_taken=f"Failed: {task}",
            method_used="agent_name",
            confidence=0.0,
            error=str(e)
        )
```

### Type-Safe Access Pattern

```python
# Execute agent
result: ActionResult = await agent.execute_task(task)

# Type-safe checks
if result.success:
    # Direct attribute access
    print(result.action_taken)

    if result.data:
        # Parse structured data
        output = result.data.get("output", {})
        if isinstance(output, dict):
            typed_output = BrowserOutput(**output)
            print(typed_output.text)
```

### Context Passing Pattern

```python
# Store internally as typed
results.append(result)  # List[ActionResult]

# Serialize for context
context["previous_results"].append(result.model_dump())

# Parse in next agent
for res in context.get("previous_results", []):
    # Extract and type
    output = res.get("data", {}).get("output")
    if isinstance(output, dict):
        typed_output = BrowserOutput(**output)
```

---

## Troubleshooting

### Agent Stuck in Loop

**Symptoms**: Same actions repeated, no progress

**Check**:

1. `action_history` for patterns
2. Loop detection logs
3. Max steps reached

**Solution**: Loop detection will trigger handoff automatically

### Wrong Element Clicked

**Symptoms**: GUI agent clicks wrong buttons

**Check**:

1. Accessibility API available?
2. OCR fuzzy matching too permissive?
3. Element identifiers in accessibility tree?

**Solution**: Enable accessibility debug output

### File Not Found

**Symptoms**: GUI agent can't find browser-downloaded files

**Check**:

1. `BrowserOutput.files` contains paths
2. Paths are absolute
3. Files actually exist

**Solution**: Check browser agent's `work_directory`

### Handoff Not Working

**Symptoms**: Task marked as failed instead of handed off

**Check**:

1. `result.handoff_requested` is True
2. `suggested_agent` is valid
3. Context being passed correctly

**Solution**: Verify `context["previous_results"]`

---

## Quick Reference

### Running the System

```bash
# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with API keys

# Run
python -m computer_use.main
```

### Testing Components

```bash
# Check permissions
python -m computer_use.utils.permissions

# Test accessibility
python -c "from computer_use.tools.accessibility import MacOSAccessibility; print(MacOSAccessibility().available)"

# Test OCR
python -c "from computer_use.tools.vision.ocr_tool import OCRTool; OCRTool().test()"
```

---

**End of Technical Reference**

_This document reflects the current state of the system as of October 2025._
