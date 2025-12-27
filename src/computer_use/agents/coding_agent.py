"""
Coding agent that wraps Cline CLI for autonomous code automation.
Similar to BrowserAgent wrapping Browser-Use library.
"""

import subprocess
import shutil
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from ..schemas.actions import ActionResult
from ..utils.ui import dashboard, ActionType, LogBatcher


MODULE_DIR = Path(__file__).parent.parent
CODE_DIR_NAME = "code"
VENV_NAME = ".venv"

class ClineOutputFormatter:
    """Formats Cline CLI output with rich UI elements."""

    def __init__(self):
        self._in_code_block = False
        self._code_lang = ""
        self._spinner_frames = ["◐", "◓", "◑", "◒"]
        self._spinner_idx = 0

    def _get_spinner(self) -> str:
        frame = self._spinner_frames[self._spinner_idx]
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        return frame

    def format_line(self, line: str) -> Optional[str]:
        """Format a single line for display. Returns None to skip."""
        stripped = line.strip()

        if stripped.startswith("```"):
            if not self._in_code_block:
                self._in_code_block = True
                self._code_lang = stripped[3:].strip() or "text"
                return f"  [dim]┌─ {self._code_lang} ─[/]"
            else:
                self._in_code_block = False
                return "  [dim]└────────────[/]"

        if self._in_code_block:
            return f"  [dim]│[/] [white]{line[:100]}[/]"

        if "### Cline is running" in line:
            cmd = line.split("`")[1] if "`" in line else "command"
            cmd = cmd[:60] + "..." if len(cmd) > 60 else cmd
            return f"  [cyan]{self._get_spinner()}[/] [bold]Running[/] [dim]{cmd}[/]"

        if "## API request completed" in line:
            if "`" in line:
                tokens = line.split("`")[1]
                return f"  [dim]⚡ {tokens}[/]"
            return None

        if "## Checkpoint created" in line:
            return "  [dim]📍[/]"

        if "thinking" in line.lower() or "## Cline" in line:
            return f"  [cyan]{self._get_spinner()}[/] [italic dim]Thinking...[/]"

        if any(x in line.lower() for x in ["created", "wrote", "written to"]):
            return f"  [green]✓[/] {stripped[:80]}"

        if "error" in line.lower() or "failed" in line.lower():
            return f"  [red]✗[/] {stripped[:80]}"

        if any(x in line.lower() for x in ["success", "passed", "complete"]):
            return f"  [green]●[/] {stripped[:80]}"

        if line.startswith("*Conversation history"):
            return None

        if not stripped:
            return None

        if stripped.startswith("##"):
            text = stripped.lstrip("#").strip()
            return f"  [dim italic]💭 {text[:80]}[/]"

        if stripped and not stripped.startswith("#"):
            return f"  [dim]│[/] {stripped[:100]}"

        return f"  [dim]│[/] {stripped[:100]}"


CODING_GUIDELINES = """
CRITICAL REQUIREMENTS - DO NOT SKIP:

1. VERIFY CODE WORKS: Do NOT stop until the code runs successfully without errors.
   - Run the code after writing it
   - Fix any errors that occur
   - Test all main functionality
   - Only finish when everything works

2. VIRTUAL ENVIRONMENT: For ANY Python dependencies:
   - Check if {venv_path} exists, if not create it: python3 -m venv {venv_path}
   - Activate it: source {venv_path}/bin/activate
   - Install dependencies: pip install <package>
   - Run code with the venv activated

3. PROJECT LOCATION: All code MUST be created in: {project_path}
   - Create this directory if it doesn't exist
   - All files for this task go here
   - Do NOT create files outside this directory

4. REQUIREMENTS FILE: ALWAYS create requirements.txt in {project_path}
   - After installing dependencies, run: pip freeze > {project_path}/requirements.txt
   - This captures all installed packages with versions
   - Must be done BEFORE marking task complete

5. COMPLETION CHECKLIST:
   [ ] Code written in {project_path}
   [ ] Dependencies installed in {venv_path}
   [ ] requirements.txt created in {project_path}
   [ ] Code executed and tested
   [ ] All errors fixed
   [ ] Program runs successfully

ACTUAL TASK:
"""


class CodingAgent:
    """
    Cline CLI wrapper for autonomous coding tasks.
    Executes coding tasks using Cline in YOLO mode.
    """

    def __init__(self, working_directory: Optional[str] = None):
        if working_directory:
            self.code_root = Path(working_directory)
        else:
            self.code_root = MODULE_DIR / CODE_DIR_NAME
        self.venv_path = self.code_root / VENV_NAME
        self.available = self._check_cline_available()
        self._log_batcher = LogBatcher(batch_size=10, timeout_sec=0.2)
        self._ensure_code_directory()

    def _check_cline_available(self) -> bool:
        """
        Check if Cline CLI is installed.

        Returns:
            True if cline command is available
        """
        return shutil.which("cline") is not None

    def _ensure_code_directory(self) -> None:
        """Create the code directory and venv if they don't exist."""
        self.code_root.mkdir(parents=True, exist_ok=True)
        dashboard.add_log_entry(ActionType.OPEN, f"Code directory: {self.code_root}")

    def _generate_project_name(self, task: str) -> str:
        """
        Generate a unique project folder name from task description.

        Args:
            task: Task description

        Returns:
            Sanitized folder name with timestamp
        """
        words = re.sub(r"[^a-zA-Z0-9\s]", "", task.lower()).split()
        slug = "_".join(words[:4]) if words else "project"
        slug = slug[:30]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_hash = hashlib.md5(task.encode()).hexdigest()[:4]

        return f"{slug}_{timestamp}_{short_hash}"

    def _get_project_path(self, task: str) -> Path:
        """
        Get or create the project directory for this task.

        Args:
            task: Task description

        Returns:
            Path to project directory
        """
        project_name = self._generate_project_name(task)
        project_path = self.code_root / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        return project_path

    async def execute_task(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
        """
        Execute coding task using Cline CLI in autonomous mode.

        Args:
            task: Natural language coding task description
            context: Optional context from previous agents

        Returns:
            ActionResult with task status and output
        """
        if not self.available:
            return ActionResult(
                success=False,
                action_taken="Cline CLI not available",
                method_used="coding",
                confidence=0.0,
                error="Cline CLI not installed. Run 'npm install -g @anthropic/cline'",
            )

        project_path = self._get_project_path(task)

        dashboard.set_agent("Coding Agent")
        dashboard.console.print(f"\n  [bold cyan]◆ Cline[/] [dim]→[/] {task[:80]}")
        dashboard.console.print(f"  [dim]  Project:[/] {project_path}")

        enhanced_task = self._build_task_with_guidelines(task, project_path, context)

        try:
            result = self._run_cline_task(enhanced_task, project_path)

            if result["success"]:
                dashboard.add_log_entry(
                    ActionType.COMPLETE,
                    "Cline completed coding task",
                    status="complete",
                )
                dashboard.clear_action()
                return ActionResult(
                    success=True,
                    action_taken=f"Completed: {task[:50]}...",
                    method_used="coding_cline",
                    confidence=1.0,
                    data={
                        "output": result.get("output", ""),
                        "task": task,
                        "project_path": str(project_path),
                        "venv_path": str(self.venv_path),
                    },
                )
            else:
                dashboard.add_log_entry(
                    ActionType.ERROR,
                    f"Cline failed: {result.get('error')}",
                    status="error",
                )
                return ActionResult(
                    success=False,
                    action_taken=f"Failed: {task[:50]}...",
                    method_used="coding_cline",
                    confidence=0.0,
                    error=result.get("error", "Cline task failed"),
                    data={
                        "output": result.get("output", ""),
                        "project_path": str(project_path),
                    },
                )

        except Exception as e:
            dashboard.add_log_entry(
                ActionType.ERROR, f"Coding agent error: {str(e)}", status="error"
            )
            return ActionResult(
                success=False,
                action_taken="Coding task exception",
                method_used="coding_cline",
                confidence=0.0,
                error=str(e),
            )

    def _build_task_with_guidelines(
        self,
        task: str,
        project_path: Path,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """
        Build enhanced task with guidelines and context.

        Args:
            task: Original task description
            project_path: Path to project directory
            context: Context from previous agents

        Returns:
            Enhanced task string with guidelines
        """
        guidelines = CODING_GUIDELINES.format(
            venv_path=str(self.venv_path),
            project_path=str(project_path),
        )

        parts = [guidelines, task]

        if context and context.get("previous_results"):
            parts.append("\n\nCONTEXT FROM PREVIOUS AGENTS:")
            for result in context["previous_results"]:
                if result.get("data"):
                    data = result["data"]
                    if isinstance(data, dict):
                        if "output" in data:
                            parts.append(f"\nPrevious output: {data['output']}")
                        if "files" in data:
                            parts.append(f"\nFiles: {', '.join(data['files'])}")

        return "\n".join(parts)

    def _run_cline_task(self, task: str, project_path: Path) -> Dict[str, Any]:
        """
        Execute Cline in oneshot autonomous mode with real-time output.

        Uses: cline -o -y "task"
        -o = oneshot (completes and exits)
        -y = YOLO/autonomous (no prompts)

        Args:
            task: Complete task description with guidelines
            project_path: Project directory for this task

        Returns:
            Dictionary with success, output, and error
        """
        dashboard.console.print(f"  [dim]  Running cline...[/]")

        formatter = ClineOutputFormatter()
        output_lines = []

        try:
            process = subprocess.Popen(
                ["cline", "-o", "-y", task],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(self.code_root),
            )

            for line in iter(process.stdout.readline, ""):
                if line:
                    clean_line = line.rstrip()
                    output_lines.append(clean_line)
                    formatted = formatter.format_line(clean_line)
                    if formatted:
                        dashboard.console.print(formatted)

            self._log_batcher.flush_now()
            process.wait(timeout=1800)
            dashboard.set_action("Cline", target="Processing")

            output = "\n".join(output_lines)

            if process.returncode == 0:
                return {"success": True, "output": output}
            else:
                return {
                    "success": False,
                    "error": f"Exit code: {process.returncode}",
                    "output": output,
                }

        except subprocess.TimeoutExpired:
            process.kill()
            return {
                "success": False,
                "error": "Cline timed out after 30 minutes",
                "output": "\n".join(output_lines),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Cline CLI not found. Install with: npm install -g @anthropic/cline",
                "output": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": "\n".join(output_lines),
            }
