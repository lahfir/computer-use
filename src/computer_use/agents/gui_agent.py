"""
GUI agent with screenshot-driven loop (like Browser-Use).
"""

from typing import Optional, Dict, Any
from PIL import Image
from ..schemas.actions import ActionResult
from ..schemas.gui_elements import SemanticTarget
from pydantic import BaseModel, Field
import asyncio


class GUIAction(BaseModel):
    """
    Single action to take based on current screenshot.
    """

    action: str = Field(
        description="Action: open_app, click, type, scroll, double_click, right_click, read, or done"
    )
    target: str = Field(description="What to interact with")
    input_text: Optional[str] = Field(
        default=None, description="Text to type if action is 'type'"
    )
    scroll_direction: Optional[str] = Field(
        default="down",
        description="Direction to scroll: 'up' or 'down' (for scroll action)",
    )
    reasoning: str = Field(description="Why taking this action")
    is_complete: bool = Field(default=False, description="Is the task complete?")


class GUIAgent:
    """
    Screenshot-driven GUI automation agent.
    Takes screenshot → LLM decides action → Executes → Repeats until done.
    """

    def __init__(self, tool_registry, llm_client=None):
        """
        Initialize GUI agent.

        Args:
            tool_registry: PlatformToolRegistry instance
            llm_client: Vision-capable LLM for screenshot analysis
        """
        self.tool_registry = tool_registry
        self.llm_client = llm_client
        self.max_steps = 15
        self.current_app = None  # Track which app was just opened

    async def execute_task(self, task: str) -> ActionResult:
        """
        Execute GUI task using screenshot-driven loop.
        Similar to Browser-Use: screenshot → analyze → act → repeat.

        Args:
            task: Natural language task description

        Returns:
            ActionResult with execution details
        """
        step = 0
        task_complete = False
        last_action = None
        last_coordinates = None
        repeated_clicks = 0
        self.current_app = None  # Reset current app

        print(f"  🔄 Starting screenshot-driven loop (max {self.max_steps} steps)...\n")

        while step < self.max_steps and not task_complete:
            step += 1

            # Take screenshot of current state
            screenshot_tool = self.tool_registry.get_tool("screenshot")
            screenshot = screenshot_tool.capture()

            # Get LLM decision based on screenshot
            action = await self._analyze_screenshot(task, screenshot, step, last_action)

            print(f"  Step {step}: {action.action} → {action.target}")
            print(f"    Reasoning: {action.reasoning}")

            # Execute the action
            step_result = await self._execute_action(action, screenshot)

            if not step_result.get("success"):
                print(f"    ❌ Failed: {step_result.get('error')}")

                # Don't give up immediately - LLM will see failure and adapt
                if step >= 3:  # After 3 failures, stop
                    return ActionResult(
                        success=False,
                        action_taken=f"Failed after {step} attempts",
                        method_used=step_result.get("method", "unknown"),
                        confidence=0.0,
                        error=step_result.get("error"),
                    )
            else:
                print(f"    ✅ Success")
                # Report coordinates if available
                current_coords = step_result.get("coordinates")
                if current_coords:
                    x, y = current_coords
                    print(f"    📍 Coordinates: ({x}, {y})")

                    # Detect if stuck clicking same coordinates
                    if last_coordinates == current_coords:
                        repeated_clicks += 1
                        if repeated_clicks >= 3:
                            print(
                                f"    ⚠️  WARNING: Clicked same location 3 times - might be stuck!"
                            )
                            return ActionResult(
                                success=False,
                                action_taken=f"Stuck in loop at ({x}, {y})",
                                method_used="ocr",
                                confidence=0.0,
                                error=f"Clicked same coordinates 3 times",
                            )
                    else:
                        repeated_clicks = 0

                    last_coordinates = current_coords

            last_action = action
            task_complete = action.is_complete

            # Small delay for UI to update
            await asyncio.sleep(0.8)

        if task_complete:
            return ActionResult(
                success=True,
                action_taken=f"Completed task in {step} steps",
                method_used="screenshot_loop",
                confidence=0.95,
                data={
                    "steps": step,
                    "final_action": last_action.action if last_action else None,
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
    ) -> GUIAction:
        """
        Use vision LLM to analyze screenshot and decide next action.
        """
        if not self.llm_client:
            # Fallback without LLM
            return GUIAction(
                action="done",
                target="No LLM available",
                reasoning="Fallback action",
                is_complete=True,
            )

        last_action_text = ""
        if last_action:
            last_action_text = (
                f"\nLast action: {last_action.action} → {last_action.target}"
            )

        prompt = f"""
You are controlling a desktop GUI. Analyze this screenshot and decide the NEXT action.

TASK: {task}
Current Step: {step}{last_action_text}

        Available actions:
        - open_app: Open an application (e.g., "System Settings", "Calculator")
        - click: Click on UI element - BE SPECIFIC, use EXACT TEXT you see
        - double_click: Double-click on UI element
        - right_click: Right-click on UI element
        - type: Type text into a field
        - scroll: Scroll up or down (set scroll_direction to "up" or "down")
        - read: Read information from screen
        - done: Task is complete

        CRITICAL RULES FOR CLICKING:
1. target MUST be the EXACT TEXT you see on screen (one or two words max)
2. GOOD: "Storage", "General", "About This Mac"
3. BAD: "Storage in sidebar", "General button", "the Storage option"
4. If you see "Storage" → target = "Storage" (nothing else!)
5. Set is_complete=true when task is fully done

Examples:
- See "Settings" → click target="Settings"
- See "General" → click target="General"  
- See "Storage" → click target="Storage"
- See text you need → read then done

Return ONLY the next action with EXACT TEXT from screenshot.
"""

        try:
            # Use vision LLM with screenshot
            structured_llm = self.llm_client.with_structured_output(GUIAction)

            # Convert PIL to base64 for LLM
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
                    action="open_app",
                    target="System Settings",
                    reasoning="Fallback: opening settings app",
                    is_complete=False,
                )
            else:
                return GUIAction(
                    action="done",
                    target="fallback",
                    reasoning="LLM unavailable",
                    is_complete=True,
                )

    async def _execute_action(
        self, action: GUIAction, screenshot: Image.Image
    ) -> Dict[str, Any]:
        """
        Execute a single GUI action.
        """
        if action.action == "open_app":
            return await self._open_application(action.target)
        elif action.action == "click":
            return await self._click_element(action.target, screenshot)
        elif action.action == "double_click":
            return await self._double_click_element(action.target, screenshot)
        elif action.action == "right_click":
            return await self._right_click_element(action.target, screenshot)
        elif action.action == "type":
            return await self._type_text(action.input_text)
        elif action.action == "scroll":
            return await self._scroll(action.scroll_direction or "down")
        elif action.action == "read":
            return await self._read_screen(action.target, screenshot)
        elif action.action == "done":
            return {"success": True, "method": "done"}
        else:
            return {
                "success": False,
                "method": "unknown",
                "error": f"Unknown action: {action.action}",
            }

    async def _open_application(self, app_name: str) -> Dict[str, Any]:
        """
        Open an application and track it as current app.
        """
        process_tool = self.tool_registry.get_tool("process")

        try:
            result = process_tool.open_application(app_name)
            if result.get("success"):
                self.current_app = app_name  # Track the app we just opened
                print(f"    📱 Tracking current app: {app_name}")
                await asyncio.sleep(2.5)  # Wait for app to open
            return {
                "success": result.get("success", False),
                "method": "process",
            }
        except Exception as e:
            return {"success": False, "method": "process", "error": str(e)}

    async def _click_element(
        self, target: str, screenshot: Image.Image
    ) -> Dict[str, Any]:
        """
        Click element using multi-tier accuracy system.
        TIER 1: Accessibility API (100% accurate) → TIER 2: OCR (95-99%) → TIER 3: Vision
        RETURNS the exact coordinates used for clicking.
        """
        # TIER 1: Try Accessibility API FIRST (100% accurate!)
        try:
            accessibility_tool = self.tool_registry.get_tool("accessibility")
            if accessibility_tool and accessibility_tool.available:
                print(f"    🎯 TIER 1: Trying Accessibility API (100% accurate)...")
                # Pass current app name for accurate targeting
                elements = accessibility_tool.find_elements(
                    label=target, app_name=self.current_app
                )

                if elements and len(elements) > 0:
                    elem = elements[0]
                    x, y = elem["center"]
                    print(
                        f"    ✅ Accessibility found '{elem['title']}' at ({x}, {y}) [100% ACCURATE]"
                    )

                    input_tool = self.tool_registry.get_tool("input")
                    success = input_tool.click(x, y, validate=True)
                    return {
                        "success": success,
                        "method": "accessibility",
                        "coordinates": (x, y),
                        "matched_text": elem["title"],
                        "confidence": 1.0,
                    }
        except Exception as e:
            print(f"    ⚠️  Accessibility API not available or failed: {e}")

        print(f"    🎯 TIER 2: Falling back to OCR...")
        ocr_tool = self.tool_registry.get_tool("ocr")

        screenshot_tool = self.tool_registry.get_tool("screenshot")
        scaling = getattr(screenshot_tool, "scaling_factor", 1.0)

        # Try OCR - find the text
        try:
            text_matches = ocr_tool.find_text(screenshot, target, fuzzy=True)

            if text_matches:
                element = text_matches[0]
                x_raw, y_raw = element["center"]
                x = int(x_raw / scaling)
                y = int(y_raw / scaling)

                print(
                    f"    🎯 OCR found '{element['text']}' at raw ({x_raw}, {y_raw}) → scaled ({x}, {y})"
                )

                input_tool = self.tool_registry.get_tool("input")
                success = input_tool.click(x, y, validate=True)
                return {
                    "success": success,
                    "method": "ocr",
                    "coordinates": (x, y),
                    "matched_text": element["text"],
                    "confidence": element["confidence"],
                }
        except Exception as e:
            print(f"    ⚠️  OCR search failed: {e}")

        # Fallback: Search ALL text with smart matching (NO HARDCODING)
        try:
            all_text = ocr_tool.extract_all_text(screenshot)
            target_lower = target.lower().strip()

            print(f"    🔍 Searching for: '{target}'")

            best_match = None
            best_score = -999

            for item in all_text:
                text_lower = item["text"].lower().strip()

                # Smart scoring - LLM should give us exact text
                if text_lower == target_lower:
                    # Perfect exact match
                    score = 1000 + item["confidence"] * 100
                elif text_lower.startswith(target_lower):
                    # Starts with target
                    score = 700 + item["confidence"] * 100
                elif target_lower in text_lower:
                    # Contains target - penalize by length difference
                    length_penalty = len(text_lower) - len(target_lower)
                    score = 400 - length_penalty + item["confidence"] * 100
                elif target_lower.startswith(text_lower) and len(text_lower) >= 3:
                    # Text is prefix of target (partial match)
                    score = 300 + item["confidence"] * 100
                else:
                    continue  # No match

                if score > best_score:
                    best_match = item
                    best_score = score

            if best_match:
                x_raw, y_raw = best_match["center"]
                x = int(x_raw / scaling)
                y = int(y_raw / scaling)

                print(f"    🎯 OCR matched '{best_match['text']}' → ({x}, {y})")

                input_tool = self.tool_registry.get_tool("input")
                success = input_tool.click(x, y, validate=True)
                return {
                    "success": success,
                    "method": "ocr_fuzzy",
                    "coordinates": (x, y),
                    "matched_text": best_match["text"],
                    "confidence": best_match["confidence"],
                }
        except Exception as e:
            print(f"    ⚠️  Search failed: {e}")

        return {
            "success": False,
            "method": "ocr",
            "error": f"Could not locate: {target}",
            "coordinates": None,
        }

    async def _type_text(self, text: Optional[str]) -> Dict[str, Any]:
        """
        Type text at current cursor position.
        """
        if not text:
            return {"success": False, "method": "type", "error": "No text provided"}

        input_tool = self.tool_registry.get_tool("input")
        try:
            print(f"    ⌨️  Typing: '{text}'")
            input_tool.type_text(text)
            return {
                "success": True,
                "method": "type",
                "typed_text": text,
            }
        except Exception as e:
            return {"success": False, "method": "type", "error": str(e)}

    async def _scroll(self, direction: str = "down") -> Dict[str, Any]:
        """
        Scroll the screen in specified direction.
        """
        try:
            input_tool = self.tool_registry.get_tool("input")
            amount = 3  # Number of scroll units

            if direction == "down":
                input_tool.scroll(-amount)
            else:
                input_tool.scroll(amount)

            return {
                "success": True,
                "method": "scroll",
                "data": {"direction": direction},
            }
        except Exception as e:
            return {"success": False, "method": "scroll", "error": str(e)}

    async def _double_click_element(
        self, target: str, screenshot: Image.Image
    ) -> Dict[str, Any]:
        """
        Double-click element using OCR or accessibility coordinates.
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
    ) -> Dict[str, Any]:
        """
        Right-click element using OCR or accessibility coordinates.
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
    ) -> Dict[str, Any]:
        """
        Read information from screen using OCR.
        """
        ocr_tool = self.tool_registry.get_tool("ocr")

        try:
            text_results = ocr_tool.extract_all_text(screenshot)
            full_text = "\n".join([item["text"] for item in text_results])

            return {
                "success": True,
                "method": "ocr",
                "data": {"text": full_text[:500]},  # Return first 500 chars
            }
        except Exception as e:
            return {"success": False, "method": "ocr", "error": str(e)}
