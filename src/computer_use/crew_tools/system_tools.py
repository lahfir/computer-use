"""
System command tool for CrewAI.
Extracted from system_agent.py, rewritten for CrewAI integration.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import subprocess
from pathlib import Path


class ExecuteCommandInput(BaseModel):
    """Input for executing shell command."""

    command: str = Field(description="Shell command to execute")
    explanation: str = Field(description="Why this command is needed")


class ExecuteShellCommandTool(BaseTool):
    """
    Execute shell command safely with validation.
    Runs commands in user home directory.
    """

    name: str = "execute_shell_command"
    description: str = """Execute shell commands safely.
    
    Examples:
    - List files: ls ~/Documents
    - Copy file: cp ~/file.txt ~/backup/
    - Find: find ~/Downloads -name "*.pdf"
    
    Always provide explanation for safety validation."""
    args_schema: type[BaseModel] = ExecuteCommandInput

    def _run(self, command: str, explanation: str) -> str:
        """
        Execute shell command with safety checks.
        Extracted from system_agent._execute_command.

        Args:
            command: Shell command
            explanation: Reasoning for command

        Returns:
            String result for CrewAI
        """
        from ..utils.ui import dashboard, ActionType

        dashboard.add_log_entry(ActionType.EXECUTE, f"Executing: {command}")

        safety_checker = self._safety_checker
        confirmation_manager = self._confirmation_manager

        if safety_checker:
            if safety_checker.is_protected_path_in_command(command):
                error_msg = f"Command targets protected system path: {command}"
                dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
                return f"ERROR: {error_msg}"

        if confirmation_manager:
            approved, reason = confirmation_manager.request_confirmation(command)
            if not approved:
                error_msg = f"User {reason} command: {command}"
                dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
                return f"ERROR: {error_msg}"

        # Execute command
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path.home()),
            )

            if result.returncode == 0:
                output_str = (
                    f"SUCCESS: Command executed successfully\nCommand: {command}\n"
                )
                if result.stdout:
                    output_str += f"Output: {result.stdout.strip()}\n"
                dashboard.add_log_entry(
                    ActionType.COMPLETE, "Command succeeded", status="complete"
                )
                return output_str
            else:
                error_str = f"FAILED: Command failed with exit code {result.returncode}\nCommand: {command}\n"
                if result.stderr:
                    error_str += f"Error: {result.stderr.strip()}\n"
                dashboard.add_log_entry(
                    ActionType.ERROR, f"Command failed: {result.stderr}", status="error"
                )
                return error_str

        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after 30s: {command}"
            dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
            return f"ERROR: {error_msg}"
        except Exception as e:
            error_msg = f"Exception executing command: {str(e)}"
            dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
            return f"ERROR: {error_msg}"
