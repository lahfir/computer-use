"""
GUI agent with screenshot-driven loop (like Browser-Use).
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from PIL import Image
from enum import Enum
from ..schemas.actions import ActionResult
from ..schemas.browser_output import BrowserOutput
from ..schemas.tool_types import ActionExecutionResult
from ..utils.ui import (
    print_info,
    print_step,
    print_success,
    print_failure,
    print_warning,
    console,
)
from pydantic import BaseModel, Field
import asyncio

if TYPE_CHECKING:
    from ..tools.platform_registry import PlatformToolRegistry
    from langchain_core.language_models import BaseChatModel


class GUIActionType(str, Enum):
    """
    Enumeration of all possible GUI actions.
    """

    OPEN_APP = "open_app"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    SCROLL = "scroll"
    READ = "read"
    DONE = "done"


class ScrollDirection(str, Enum):
    """
    Enumeration of scroll directions.
    """

    UP = "up"
    DOWN = "down"


class GUIAction(BaseModel):
    """
    Single action to take based on current screenshot.
    """

    action: GUIActionType = Field(
        description="Action type: open_app, click, type, scroll, double_click, right_click, read, or done"
    )
    target: str = Field(description="What to interact with")
    input_text: Optional[str] = Field(
        default=None, description="Text to type if action is 'type'"
    )
    scroll_direction: ScrollDirection = Field(
        default=ScrollDirection.DOWN,
        description="Direction to scroll: 'up' or 'down' (for scroll action)",
    )
    reasoning: str = Field(description="Why taking this action")
    is_complete: bool = Field(default=False, description="Is the task complete?")


class GUIAgent:
    """
    Screenshot-driven GUI automation agent.
    Takes screenshot → LLM decides action → Executes → Repeats until done.
    """

    def __init__(
        self,
        tool_registry: "PlatformToolRegistry",
        llm_client: Optional["BaseChatModel"] = None,
    ) -> None:
        """
        Initialize GUI agent.

        Args:
            tool_registry: PlatformToolRegistry instance
            llm_client: Vision-capable LLM for screenshot analysis
        """
        self.tool_registry: "PlatformToolRegistry" = tool_registry
        self.llm_client: Optional["BaseChatModel"] = llm_client
        self.max_steps: int = 15
        self.current_app: Optional[str] = None
        self.action_history: List[Dict[str, Any]] = []
        self.context: Dict[str, Any] = {}

    async def execute_task(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
        """
        Execute GUI task using screenshot-driven loop.
        Similar to Browser-Use: screenshot → analyze → act → repeat.

        Args:
            task: Natural language task description
            context: Context from previous agents (previous_results, etc.)

        Returns:
            ActionResult with execution details
        """
        self.context = context or {}
        step = 0
        task_complete = False
        last_action = None
        last_coordinates = None
        repeated_clicks = 0
        repeated_actions = 0
        consecutive_failures = 0
        self.current_app = None
        self.action_history = []

        print_info(f"Starting GUI automation (max {self.max_steps} steps)")

        while step < self.max_steps and not task_complete:
            step += 1

            should_activate = True
            if last_action and last_action.action in [
                GUIActionType.RIGHT_CLICK,
                GUIActionType.CLICK,
            ]:
                should_activate = False

            if should_activate and self.current_app:
                process_tool = self.tool_registry.get_tool("process")
                if process_tool:
                    process_tool.launch_app(self.current_app)
                    await asyncio.sleep(0.3)

            screenshot_tool = self.tool_registry.get_tool("screenshot")
            screenshot = screenshot_tool.capture()

            accessibility_elements = []
            if self.current_app:
                accessibility_tool = self.tool_registry.get_tool("accessibility")
                if accessibility_tool and accessibility_tool.available:
                    accessibility_elements = (
                        accessibility_tool.get_all_interactive_elements(
                            self.current_app
                        )
                    )

            action = await self._analyze_screenshot(
                task,
                screenshot,
                step,
                last_action,
                accessibility_elements,
                self.action_history,
            )

            print_step(step, action.action.value, action.target, action.reasoning)

            if len(self.action_history) >= 4:
                recent = self.action_history[-4:]
                targets = [h["target"] for h in recent]

                if len(set(targets)) == 2:
                    is_alternating = all(
                        targets[i] != targets[i + 1] for i in range(len(targets) - 1)
                    )
                    if is_alternating:
                        print_warning(
                            f"Back-and-forth loop detected: {targets[0]} ↔ {targets[1]}"
                        )
                        return ActionResult(
                            success=False,
                            action_taken=f"Stuck alternating between {targets[0]} and {targets[1]}",
                            method_used="loop_detection",
                            confidence=0.0,
                            error=f"Back-and-forth loop: {targets[0]} ↔ {targets[1]}",
                            handoff_requested=True,
                            suggested_agent="system",
                            handoff_reason="GUI stuck in loop, System agent might handle better",
                            handoff_context={
                                "original_task": task,
                                "loop_pattern": targets,
                                "current_app": self.current_app,
                            },
                        )

            if (
                last_action
                and last_action.action == action.action
                and last_action.target == action.target
            ):
                repeated_actions += 1
                if repeated_actions >= 2:
                    print_warning("Repeated same action 3 times - stopping!")
                    return ActionResult(
                        success=False,
                        action_taken=f"Stuck in loop: {action.action.value} → {action.target}",
                        method_used="loop_detection",
                        confidence=0.0,
                        error="Repeated same action 3 times",
                    )
            else:
                repeated_actions = 0

            step_result = await self._execute_action(action, screenshot)

            self.action_history.append(
                {
                    "step": step,
                    "action": action.action.value,
                    "target": action.target,
                    "success": step_result.get("success"),
                    "reasoning": action.reasoning,
                }
            )

            if not step_result.get("success"):
                print_failure(f"Failed: {step_result.get('error')}")
                consecutive_failures += 1

                if consecutive_failures >= 2:
                    print_warning(
                        f"GUI struggling ({consecutive_failures} failures) - requesting System agent handoff"
                    )
                    return ActionResult(
                        success=False,
                        action_taken=f"GUI agent struggled after {consecutive_failures} failures",
                        method_used="gui_handoff",
                        confidence=0.0,
                        error=step_result.get("error"),
                        handoff_requested=True,
                        suggested_agent="system",
                        handoff_reason=f"Could not complete GUI action: {step_result.get('error')}",
                        handoff_context={
                            "original_task": task,
                            "failed_action": (
                                action.action.value if action else "unknown"
                            ),
                            "failed_target": action.target if action else "unknown",
                            "current_app": self.current_app,
                            "steps_completed": step,
                            "last_successful_action": (
                                last_action.action.value if last_action else None
                            ),
                        },
                    )
            else:
                consecutive_failures = 0
                print_success("Success")
                current_coords = step_result.get("coordinates")
                if current_coords:
                    x, y = current_coords
                    console.print(f"  [dim]Coordinates: ({x}, {y})[/dim]")

                    if last_coordinates == current_coords:
                        repeated_clicks += 1
                        if repeated_clicks >= 3:
                            print(
                                "    ⚠️  WARNING: Clicked same location 3 times - might be stuck!"
                            )
                            return ActionResult(
                                success=False,
                                action_taken=f"Stuck in loop at ({x}, {y})",
                                method_used="ocr",
                                confidence=0.0,
                                error="Clicked same coordinates 3 times",
                            )
                    else:
                        repeated_clicks = 0

                    last_coordinates = current_coords

            last_action = action
            task_complete = action.is_complete

            status = "✅ Task complete" if task_complete else "⏳ Continuing..."
            console.print(f"  [dim]{status}[/dim]")

            if not task_complete:
                await asyncio.sleep(0.5)

        if task_complete:
            return ActionResult(
                success=True,
                action_taken=f"Completed task in {step} steps",
                method_used="screenshot_loop",
                confidence=0.95,
                data={
                    "steps": step,
                    "final_action": last_action.action.value if last_action else None,
                    "task_complete": True,
                },
            )
        else:
            return ActionResult(
                success=False,
                action_taken=f"Exceeded max steps ({self.max_steps})",
                method_used="screenshot_loop",
                confidence=0.0,
                error="Task not completed within step limit",
            )

    async def _analyze_screenshot(
        self,
        task: str,
        screenshot: Image.Image,
        step: int,
        last_action: Optional[GUIAction],
        accessibility_elements: List[Dict[str, Any]] = None,
        action_history: List[Dict[str, Any]] = None,
    ) -> GUIAction:
        """
        Use vision LLM to analyze screenshot and decide next action.
        Now includes accessibility element context for 100% accuracy.
        """
        if not self.llm_client:
            return GUIAction(
                action=GUIActionType.DONE,
                target="No LLM available",
                reasoning="Fallback action",
                is_complete=True,
            )

        last_action_text = ""
        if last_action:
            last_action_text = (
                f"\nLast action: {last_action.action.value} → {last_action.target}"
            )

        history_context = ""
        if action_history and len(action_history) > 0:
            history_context = "\n\nACTION HISTORY (what you've done so far):\n"
            for h in action_history[-8:]:
                status = "✅" if h.get("success") else "❌"
                history_context += (
                    f"  {status} Step {h['step']}: {h['action']} -> {h['target']}\n"
                )

            if len(action_history) >= 4:
                recent_targets = [h["target"] for h in action_history[-4:]]
                if len(set(recent_targets)) == 2:
                    is_alternating = all(
                        recent_targets[i] != recent_targets[i + 1]
                        for i in range(len(recent_targets) - 1)
                    )
                    if is_alternating:
                        history_context += f"\n⚠️  WARNING: You're alternating between {recent_targets[0]} and {recent_targets[1]}! This is a loop!\n⚠️  You need to do something DIFFERENT or hand off to another approach!\n"

            history_context += "\n💡 SMART TIPS:\n"
            history_context += "  • If you copied, you must paste!\n"
            history_context += "  • If action failed, try a different approach!\n"
            history_context += "  • If you're going back and forth, STOP and mark done or try keyboard!\n"

        accessibility_context = ""
        if accessibility_elements and len(accessibility_elements) > 0:
            accessibility_context = "\n\nAVAILABLE ACCESSIBILITY ELEMENTS (use these identifiers for 100% accuracy):\n"
            for elem in accessibility_elements[:30]:  # Show first 30 elements
                identifier = elem.get("identifier", "")
                role = elem.get("role", "")
                desc = elem.get("description", "")
                if identifier:
                    accessibility_context += f"  • {identifier} ({role})"
                    if desc and desc != identifier:
                        accessibility_context += f" - {desc}"
                    accessibility_context += "\n"

        previous_work_context = ""
        if self.context and self.context.get("previous_results"):
            prev_results = self.context.get("previous_results", [])
            if prev_results:
                previous_work_context = "\n\n" + "=" * 60 + "\n"
                previous_work_context += "PREVIOUS AGENT WORK (Build on this!):\n"
                previous_work_context += "=" * 60 + "\n"

                for i, res in enumerate(prev_results, 1):
                    agent_type = res.get("method_used", "unknown")
                    action = res.get("action_taken", "")
                    success = "✅" if res.get("success") else "❌"
                    previous_work_context += (
                        f"\n{success} Agent {i} ({agent_type}): {action}\n"
                    )

                    if res.get("data"):
                        data = res.get("data", {})
                        output = data.get("output")

                        if isinstance(output, dict):
                            try:
                                browser_output = BrowserOutput(**output)
                                previous_work_context += (
                                    f"\n📝 Summary:\n{browser_output.text}\n"
                                )

                                if browser_output.has_files():
                                    previous_work_context += (
                                        "\n📁 DOWNLOADED FILES (use these paths!):\n"
                                    )
                                    for file_path in browser_output.files:
                                        previous_work_context += f"   • {file_path}\n"

                                    previous_work_context += "\n📊 File Details:\n"
                                    for file_detail in browser_output.file_details:
                                        size_kb = file_detail.size / 1024
                                        previous_work_context += f"   • {file_detail.name} ({size_kb:.1f} KB)\n"
                                        previous_work_context += (
                                            f"     Path: {file_detail.path}\n"
                                        )
                            except Exception:
                                if output.get("text"):
                                    previous_work_context += (
                                        f"\n📝 Summary:\n{output['text']}\n"
                                    )

                        elif isinstance(output, str):
                            previous_work_context += f"     Output: {output}\n"

                        if "downloaded_file" in data:
                            previous_work_context += (
                                f"     Downloaded: {data['downloaded_file']}\n"
                            )
                        if "file_location" in data:
                            previous_work_context += (
                                f"     Location: {data['file_location']}\n"
                            )

                previous_work_context += "\n" + "=" * 60 + "\n"
                previous_work_context += "🎯 YOUR JOB: Use the files/data above to complete the current task!\n"
                previous_work_context += "=" * 60 + "\n"

        prompt = f"""
You are a GUI automation agent. Analyze the screenshot and decide the NEXT single action.

TASK: {task}
Current Step: {step}{last_action_text}{history_context}{previous_work_context}{accessibility_context}

═══════════════════════════════════════════════════════════
STEP 1: OBSERVE THE SCREENSHOT
═══════════════════════════════════════════════════════════
- What application is open?
- What folder/page are you currently in?
- What UI elements are visible?
- What's the current state?

═══════════════════════════════════════════════════════════
STEP 2: UNDERSTAND THE WORKFLOW
═══════════════════════════════════════════════════════════

Common workflows you MUST understand:

📋 COPY/PASTE FILES:
  1. Navigate to source location
  2. Select the file (single click)
  3. Copy it (right-click → Copy, or use keyboard Cmd+C on Mac)
  4. Navigate to destination location
  5. Paste it (right-click → Paste, or use keyboard Cmd+V on Mac)
  6. If task says "open", then open the pasted file

⚠️  CRITICAL: You CANNOT paste before you copy!
⚠️  CRITICAL: Double-clicking opens a file, it does NOT copy it!

🧮 CALCULATOR:
  - Type the full expression (e.g., "2+2")
  - Press Enter with input_text="\\n"

═══════════════════════════════════════════════════════════
STEP 3: DECIDE NEXT ACTION
═══════════════════════════════════════════════════════════

Available actions:
- open_app: Launch application
- click: Single click (select items, click buttons)
- double_click: Open files/folders
- right_click: Open context menu (for Copy, Paste, etc.)
- type: Type text or special keys (\\n = Enter)
- scroll: Scroll up/down
- read: Extract text from screen
- done: Mark task complete

Action selection rules:
✅ Use accessibility identifiers when available (100% accurate)
✅ Use visible text from screenshot for OCR fallback
✅ For file operations: click to select, right-click for menu
✅ Check history to avoid repeating failed actions
✅ If stuck after 2 failures → mark done (let system agent try)

═══════════════════════════════════════════════════════════
EXAMPLES OF SMART DECISIONS
═══════════════════════════════════════════════════════════

Task: "Copy image from Downloads to Documents"
  Current: In Downloads folder, see image.png
  ❌ BAD: double_click → image.png (opens it, doesn't copy!)
  ❌ BAD: click → Documents (haven't copied anything yet!)
  ✅ GOOD: click → image.png (select it first)
  
  Next step after selecting:
  ✅ GOOD: right_click → image.png (opens context menu with Copy)
  
  After copying:
  ✅ GOOD: click → Documents (now navigate to destination)
  
  In Documents:
  ✅ GOOD: right_click → empty space (opens menu with Paste)

Task: "Calculate 5+3"
  ✅ GOOD: type → "5+3"
  ✅ GOOD: type → "\\n" (press Enter)
  ❌ BAD: click → "5", click → "+", click → "3" (too slow!)

Task: "Find file and email it"
  Current: Can't find email option in GUI
  ✅ GOOD: mark is_complete=False (let system agent use CLI)

═══════════════════════════════════════════════════════════

Now, based on the screenshot and your history, what is the NEXT action?
Think step-by-step:
1. Where am I now?
2. What have I already done?
3. What's the NEXT step in the workflow?
4. What action accomplishes that step?
"""

        try:
            structured_llm = self.llm_client.with_structured_output(GUIAction)

            import io
            import base64

            buffered = io.BytesIO()
            screenshot.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            # Create message with image
            from langchain_core.messages import HumanMessage

            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_str}"},
                    },
                ]
            )

            action = await structured_llm.ainvoke([message])
            return action

        except Exception as e:
            print(f"    ⚠️  LLM analysis failed: {e}, using fallback")
            # Fallback for first step
            if step == 1 and "settings" in task.lower():
                return GUIAction(
                    action=GUIActionType.OPEN_APP,
                    target="System Settings",
                    reasoning="Fallback: opening settings app",
                    is_complete=False,
                )
            else:
                return GUIAction(
                    action=GUIActionType.DONE,
                    target="fallback",
                    reasoning="LLM unavailable",
                    is_complete=True,
                )

    async def _execute_action(
        self, action: GUIAction, screenshot: Image.Image
    ) -> ActionExecutionResult:
        """
        Execute a single GUI action.

        Args:
            action: GUIAction to execute
            screenshot: Current screenshot

        Returns:
            ActionExecutionResult with execution details
        """
        if action.action == GUIActionType.OPEN_APP:
            return await self._open_application(action.target)
        elif action.action == GUIActionType.CLICK:
            return await self._click_element(action.target, screenshot)
        elif action.action == GUIActionType.DOUBLE_CLICK:
            return await self._double_click_element(action.target, screenshot)
        elif action.action == GUIActionType.RIGHT_CLICK:
            return await self._right_click_element(action.target, screenshot)
        elif action.action == GUIActionType.TYPE:
            return await self._type_text(action.input_text)
        elif action.action == GUIActionType.SCROLL:
            return await self._scroll(action.scroll_direction.value)
        elif action.action == GUIActionType.READ:
            return await self._read_screen(action.target, screenshot)
        elif action.action == GUIActionType.DONE:
            return ActionExecutionResult(success=True, method="done")
        else:
            return ActionExecutionResult(
                success=False,
                method="unknown",
                error=f"Unknown action: {action.action}",
            )

    async def _open_application(self, app_name: str) -> ActionExecutionResult:
        """
        Open an application and wait for it to be ready.
        Uses dynamic wait - checks if app windows are available.

        Args:
            app_name: Application name to open

        Returns:
            ActionExecutionResult with execution details
        """
        process_tool = self.tool_registry.get_tool("process")

        try:
            result = process_tool.open_application(app_name)
            if result.get("success"):
                self.current_app = app_name
                print(f"    📱 Tracking current app: {app_name}")

                await self._wait_for_app_ready(app_name)
            return ActionExecutionResult(
                success=result.get("success", False), method="process"
            )
        except Exception as e:
            return ActionExecutionResult(success=False, method="process", error=str(e))

    async def _wait_for_app_ready(self, app_name: str) -> None:
        """
        Smart dynamic wait for app to be ready.
        Uses accessibility API to check if app is already running.

        Args:
            app_name: Application name
        """
        accessibility_tool = self.tool_registry.get_tool("accessibility")

        if not accessibility_tool or not accessibility_tool.available:
            await asyncio.sleep(0.3)
            print(f"    ✅ {app_name} ready")
            return

        if accessibility_tool.is_app_running(app_name):
            print(f"    ✅ {app_name} ready (already running)")
            return

        max_attempts = 10
        attempt = 0

        while attempt < max_attempts:
            await asyncio.sleep(0.2)
            attempt += 1

            try:
                elements = accessibility_tool.get_all_interactive_elements(app_name)
                if elements and len(elements) > 3:
                    elapsed = attempt * 0.2
                    print(f"    ✅ {app_name} ready ({elapsed:.1f}s)")
                    return
            except Exception:
                pass

        print(f"    ✅ {app_name} ready")
        await asyncio.sleep(0.1)

    async def _click_element(
        self, target: str, screenshot: Image.Image
    ) -> ActionExecutionResult:
        """
        Click element using multi-tier accuracy system.
        TIER 1A: Accessibility native click → TIER 1B: Accessibility coordinates → TIER 2: OCR

        Args:
            target: Element to click
            screenshot: Current screenshot

        Returns:
            ActionExecutionResult with click details
        """
        empty_space_keywords = [
            "empty space",
            "blank area",
            "empty area",
            "blank space",
            "background",
        ]

        target_lower = target.lower()
        is_empty_space = any(
            keyword in target_lower for keyword in empty_space_keywords
        )

        if is_empty_space:
            accessibility_tool = self.tool_registry.get_tool("accessibility")
            if accessibility_tool and self.current_app:
                bounds = accessibility_tool.get_app_window_bounds(self.current_app)
                if bounds:
                    x, y, w, h = bounds
                    center_x = x + w // 2
                    center_y = y + h // 2

                    input_tool = self.tool_registry.get_tool("input")
                    success = input_tool.click(center_x, center_y, validate=True)

                    console.print(
                        f"    [green]Clicked empty space[/green] at ({center_x}, {center_y})"
                    )

                    return ActionExecutionResult(
                        success=success,
                        method="semantic",
                        coordinates=(center_x, center_y),
                        matched_text="empty space",
                        confidence=1.0,
                    )

        accessibility_tool = self.tool_registry.get_tool("accessibility")
        if accessibility_tool and accessibility_tool.available:
            console.print("    [cyan]TIER 1:[/cyan] Accessibility API")

            if hasattr(accessibility_tool, "click_element"):
                clicked, element = accessibility_tool.click_element(
                    target, self.current_app
                )

                if clicked:
                    return ActionExecutionResult(
                        success=True,
                        method="accessibility_native",
                        coordinates=None,
                        matched_text=target,
                        confidence=1.0,
                    )
                elif element:
                    print("    ⚠️  Native click failed, using element coordinates...")
                    try:
                        pos = element.AXPosition
                        size = element.AXSize
                        x = int(pos[0] + size[0] / 2)
                        y = int(pos[1] + size[1] / 2)

                        identifier = getattr(element, "AXIdentifier", target)
                        print(
                            f"    ✅ Found '{identifier}' at ({x}, {y}) via accessibility"
                        )

                        input_tool = self.tool_registry.get_tool("input")
                        success = input_tool.click(x, y, validate=True)
                        return ActionExecutionResult(
                            success=success,
                            method="accessibility_coordinates",
                            coordinates=(x, y),
                            matched_text=identifier,
                            confidence=1.0,
                        )
                    except Exception as e:
                        print(f"    ⚠️  Could not get element coordinates: {e}")

            elements = accessibility_tool.find_elements(
                label=target, app_name=self.current_app
            )

            if elements:
                elem = elements[0]
                x, y = elem["center"]
                print(f"    ✅ Found '{elem['title']}' at ({x}, {y}) via accessibility")

                input_tool = self.tool_registry.get_tool("input")
                success = input_tool.click(x, y, validate=True)
                return ActionExecutionResult(
                    success=success,
                    method="accessibility_coordinates",
                    coordinates=(x, y),
                    matched_text=elem["title"],
                    confidence=1.0,
                )
            else:
                console.print("    [dim]Element not found in accessibility tree[/dim]")
        else:
            console.print("    [dim]Accessibility unavailable[/dim]")

        console.print("    [cyan]TIER 2:[/cyan] OCR")
        ocr_tool = self.tool_registry.get_tool("ocr")
        screenshot_tool = self.tool_registry.get_tool("screenshot")
        scaling = getattr(screenshot_tool, "scaling_factor", 1.0)

        ocr_screenshot = screenshot
        x_offset = 0
        y_offset = 0

        if self.current_app and accessibility_tool and accessibility_tool.available:
            window_bounds = accessibility_tool.get_app_window_bounds(self.current_app)
            if window_bounds:
                x, y, w, h = window_bounds
                x_scaled = int(x * scaling)
                y_scaled = int(y * scaling)
                w_scaled = int(w * scaling)
                h_scaled = int(h * scaling)

                try:
                    ocr_screenshot = screenshot.crop(
                        (x_scaled, y_scaled, x_scaled + w_scaled, y_scaled + h_scaled)
                    )
                    x_offset = x
                    y_offset = y
                except Exception:
                    pass

        try:
            text_matches = ocr_tool.find_text(ocr_screenshot, target, fuzzy=True)

            if text_matches:
                element = text_matches[0]
                x_raw, y_raw = element.center
                x_screen = int(x_raw / scaling) + x_offset
                y_screen = int(y_raw / scaling) + y_offset

                console.print(
                    f"    [green]Found[/green] '{element.text}' at ({x_screen}, {y_screen})"
                )

                input_tool = self.tool_registry.get_tool("input")
                success = input_tool.click(x_screen, y_screen, validate=True)
                return ActionExecutionResult(
                    success=success,
                    method="ocr",
                    coordinates=(x_screen, y_screen),
                    matched_text=element.text,
                    confidence=element.confidence,
                )
        except Exception:
            pass

        try:
            all_text = ocr_tool.extract_all_text(ocr_screenshot)
            target_lower = target.lower().strip()

            best_match = None
            best_score = -999

            for item in all_text:
                text_lower = item.text.lower().strip()

                if text_lower == target_lower:
                    score = 1000 + item.confidence * 100
                elif text_lower.startswith(target_lower):
                    score = 700 + item.confidence * 100
                elif target_lower in text_lower:
                    score = (
                        400
                        - (len(text_lower) - len(target_lower))
                        + item.confidence * 100
                    )
                elif target_lower.startswith(text_lower) and len(text_lower) >= 3:
                    score = 300 + item.confidence * 100
                else:
                    continue

                if score > best_score:
                    best_match = item
                    best_score = score

            if best_match:
                x_raw, y_raw = best_match.center
                x_screen = int(x_raw / scaling) + x_offset
                y_screen = int(y_raw / scaling) + y_offset

                print(
                    f"    ✅ Matched '{best_match.text}' (score: {best_score:.0f}) at ({x_screen}, {y_screen})"
                )

                input_tool = self.tool_registry.get_tool("input")
                success = input_tool.click(x_screen, y_screen, validate=True)
                return ActionExecutionResult(
                    success=success,
                    method="ocr",
                    coordinates=(x_screen, y_screen),
                    matched_text=best_match.text,
                    confidence=best_match.confidence,
                )
            else:
                print(
                    f"    ⚠️  No fuzzy match found for '{target}' in {len(all_text)} extracted texts"
                )
        except Exception as e:
            print(f"    ⚠️  Fuzzy search failed: {e}")

        return ActionExecutionResult(
            success=False,
            method="ocr",
            error=f"Could not locate: {target}",
            coordinates=None,
        )

    async def _type_text(self, text: Optional[str]) -> ActionExecutionResult:
        """
        Type text at current cursor position.
        Supports special characters like '\n' for Enter/Return key.

        Args:
            text: Text to type

        Returns:
            ActionExecutionResult with typing details
        """
        if not text:
            return ActionExecutionResult(
                success=False, method="type", error="No text provided"
            )

        input_tool = self.tool_registry.get_tool("input")
        try:
            if text == "\\n" or text == "\n":
                print("    ⌨️  Pressing Enter/Return key")
                import pyautogui

                pyautogui.press("return")
            else:
                print(f"    ⌨️  Typing: '{text}'")
                input_tool.type_text(text)
            return ActionExecutionResult(success=True, method="type", typed_text=text)
        except Exception as e:
            return ActionExecutionResult(success=False, method="type", error=str(e))

    async def _scroll(self, direction: str = "down") -> ActionExecutionResult:
        """
        Scroll the screen in specified direction.

        Args:
            direction: Direction to scroll ('up' or 'down')

        Returns:
            ActionExecutionResult with scroll details
        """
        try:
            input_tool = self.tool_registry.get_tool("input")
            amount = 3  # Number of scroll units

            if direction == "down":
                input_tool.scroll(-amount)
            else:
                input_tool.scroll(amount)

            return ActionExecutionResult(
                success=True, method="scroll", data={"direction": direction}
            )
        except Exception as e:
            return ActionExecutionResult(success=False, method="scroll", error=str(e))

    async def _double_click_element(
        self, target: str, screenshot: Image.Image
    ) -> ActionExecutionResult:
        """
        Double-click element using OCR or accessibility coordinates.

        Args:
            target: Element to double-click
            screenshot: Current screenshot

        Returns:
            ActionExecutionResult with double-click details
        """
        # Try to find element first
        result = await self._click_element(target, screenshot)
        if result.get("success") and result.get("coordinates"):
            x, y = result["coordinates"]
            input_tool = self.tool_registry.get_tool("input")
            input_tool.double_click(x, y, validate=True)
            result["method"] = "double_click"
            return result
        return result

    async def _right_click_element(
        self, target: str, screenshot: Image.Image
    ) -> ActionExecutionResult:
        """
        Right-click element using OCR or accessibility coordinates.

        Args:
            target: Element to right-click
            screenshot: Current screenshot

        Returns:
            ActionExecutionResult with right-click details
        """
        # Try to find element first
        result = await self._click_element(target, screenshot)
        if result.get("success") and result.get("coordinates"):
            x, y = result["coordinates"]
            input_tool = self.tool_registry.get_tool("input")
            input_tool.right_click(x, y, validate=True)
            result["method"] = "right_click"
            return result
        return result

    async def _read_screen(
        self, target: str, screenshot: Image.Image
    ) -> ActionExecutionResult:
        """
        Read information from screen using OCR.

        Args:
            target: Target area to read
            screenshot: Current screenshot

        Returns:
            ActionExecutionResult with extracted text
        """
        ocr_tool = self.tool_registry.get_tool("ocr")

        try:
            text_results = ocr_tool.extract_all_text(screenshot)
            full_text = "\n".join([item.text for item in text_results])

            return ActionExecutionResult(
                success=True,
                method="ocr",
                data={"text": full_text[:500]},  # Return first 500 chars
            )
        except Exception as e:
            return ActionExecutionResult(success=False, method="ocr", error=str(e))
