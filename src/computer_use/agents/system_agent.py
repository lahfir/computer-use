"""
System agent that uses shell commands dynamically.
LLM generates commands iteratively based on output.
"""

from typing import TYPE_CHECKING, List
import subprocess
from ..schemas.actions import (
    ActionResult,
    CommandResult,
    ShellCommand,
    SystemResultData,
    HandoffContext,
    SystemCommandHistoryEntry,
)
from ..utils.ui import print_info, print_success, print_failure, console
from ..utils.platform_helper import PlatformHelper

if TYPE_CHECKING:
    from ..schemas.workflow import WorkflowContext


class SystemAgent:
    """
    Shell-command driven system agent.
    Uses LLM to generate commands iteratively.
    """

    def __init__(self, tool_registry, safety_checker, llm_client=None):
        """
        Initialize system agent.

        Args:
            tool_registry: PlatformToolRegistry instance
            safety_checker: SafetyChecker for validating operations
            llm_client: LLM for generating shell commands
        """
        self.tool_registry = tool_registry
        self.safety_checker = safety_checker
        self.llm_client = llm_client
        self.max_steps = 10
        self.command_history: List[SystemCommandHistoryEntry] = []
        self.platform_helper = PlatformHelper()

    async def execute_task(
        self, task: str, context: "WorkflowContext | None" = None
    ) -> ActionResult:
        """
        Execute task by generating shell commands iteratively.

        Args:
            task: Natural language task description
            context: Optional WorkflowContext from previous agents

        Returns:
            ActionResult with task status
        """
        if not self.llm_client:
            return ActionResult(
                success=False,
                action_taken="No LLM available",
                method_used="system",
                confidence=0.0,
                error="System agent requires LLM",
            )

        self.command_history = []
        step = 0
        task_complete = False
        last_output = ""

        print_info(f"Starting shell command loop (max {self.max_steps} steps)")

        while step < self.max_steps and not task_complete:
            step += 1

            command_decision = await self._get_next_command(
                task, context, last_output, step
            )

            console.print(f"\n[bold cyan]Step {step}:[/bold cyan]")
            console.print(f"  [dim]Reasoning: {command_decision.reasoning}[/dim]")

            if command_decision.needs_handoff:
                print_info(f"Requesting handoff to {command_decision.handoff_agent}")
                return ActionResult(
                    success=False,
                    action_taken=f"Needs {command_decision.handoff_agent} agent",
                    method_used="system_shell",
                    confidence=0.0,
                    handoff_requested=True,
                    suggested_agent=command_decision.handoff_agent,
                    handoff_reason=command_decision.handoff_reason,
                    handoff_context=HandoffContext(
                        original_task=task,
                        system_progress=self.command_history,
                        last_output=last_output,
                    ),
                )

            command = command_decision.command

            if command:
                console.print(f"  [yellow]Command:[/yellow] [cyan]{command}[/cyan]")

                result = self._execute_command(command)
                self.command_history.append(
                    SystemCommandHistoryEntry(
                        command=command,
                        output=result.output or "",
                        success=result.success,
                    )
                )

                if not result.success:
                    print_failure(f"Failed: {result.error}")
                    last_output = f"ERROR: {result.error}"
                else:
                    output = (result.output or "").strip()
                    if output:
                        console.print(
                            f"  [green]Output:[/green] {output[:200]}{'...' if len(output) > 200 else ''}"
                        )
                        last_output = output
                    else:
                        print_success("Success (no output)")
                        last_output = "Command succeeded"

            if command_decision.is_complete:
                print_success("Task complete")
                task_complete = True
                break

        if task_complete:
            return ActionResult(
                success=True,
                action_taken=f"Completed in {step} commands",
                method_used="system_shell",
                confidence=1.0,
                data=SystemResultData(commands=self.command_history),
            )
        else:
            return ActionResult(
                success=False,
                action_taken=f"Exceeded {self.max_steps} steps",
                method_used="system_shell",
                confidence=0.0,
                error="Task not completed within step limit",
            )

    async def _get_next_command(
        self,
        task: str,
        context: "WorkflowContext | None",
        last_output: str,
        step: int,
    ) -> ShellCommand:
        """
        Ask LLM for next shell command based on current state.

        Args:
            task: Original task
            context: WorkflowContext with previous agent results
            last_output: Output from last command
            step: Current step number

        Returns:
            ShellCommand decision
        """
        prompt = f"""
You are a shell command agent. Generate ONE shell command at a time to accomplish the task.

TASK: {task}
"""

        if context and context.agent_results:
            prompt += "\n\nPREVIOUS AGENT WORK:\n"
            for res in context.agent_results:
                status = "✅" if res.success else "❌"
                prompt += f"{status} {res.agent}: {res.subtask}\n"
            prompt += "\n"

        if self.command_history:
            prompt += "\nCOMMAND HISTORY:\n"
            for i, cmd in enumerate(self.command_history[-3:], 1):
                prompt += f"  {i}. {cmd.command}\n"
                if cmd.output:
                    prompt += f"     Output: {cmd.output[:100]}...\n"

        if last_output:
            prompt += f"\nLAST OUTPUT:\n{last_output}\n"

        platform_guidelines = self.platform_helper.get_shell_command_guidelines()

        prompt += f"""
{platform_guidelines}

GUIDELINES:
1. Generate ONE command to progress toward the goal
2. Use the platform-specific commands above
3. If task needs GUI interaction (e.g., edit file content), set needs_handoff=true
4. Set is_complete=true when task is fully done
5. Use full paths (~/Documents, ~/Downloads, etc.)

CURRENT STEP: {step}

Generate the next command:
"""

        try:
            structured_llm = self.llm_client.with_structured_output(ShellCommand)
            decision = await structured_llm.ainvoke(prompt)
            return decision
        except Exception as e:
            console.print(f"  [yellow]Warning: LLM error: {e}[/yellow]")
            return ShellCommand(
                command="echo 'error'",
                reasoning="LLM failed",
                is_complete=True,
            )

    def _execute_command(self, command: str) -> CommandResult:
        """
        Execute shell command safely.

        Args:
            command: Shell command to execute

        Returns:
            CommandResult with output or error
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(__import__("pathlib").Path.home()),
            )

            if result.returncode == 0:
                return CommandResult(
                    success=True, command=command, output=result.stdout
                )
            else:
                return CommandResult(
                    success=False,
                    command=command,
                    error=result.stderr or "Command failed",
                )

        except subprocess.TimeoutExpired:
            return CommandResult(
                success=False, command=command, error="Command timed out (30s)"
            )
        except Exception as e:
            return CommandResult(success=False, command=command, error=str(e))
