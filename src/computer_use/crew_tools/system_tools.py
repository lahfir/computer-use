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
        from ..utils.ui import print_info

        print_info(f"⚙️ Executing command: {command}")

        # Safety check
        safety_checker = self._safety_checker
        if safety_checker:
            if safety_checker.is_destructive(command):
                error_msg = f"ERROR: Command is potentially destructive and was blocked - {command}"
                print_info(f"❌ {error_msg}")
                return error_msg

        # Confirmation check
        confirmation_manager = self._confirmation_manager
        if confirmation_manager and safety_checker:
            requires_confirmation = safety_checker.requires_confirmation(command)
            if requires_confirmation:
                approved, reason = confirmation_manager.request_confirmation(command)
                if not approved:
                    error_msg = f"ERROR: User {reason} command - {command}"
                    print_info(f"❌ {error_msg}")
                    return error_msg

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
                print_info("✅ Command succeeded")
                return output_str
            else:
                error_str = f"FAILED: Command failed with exit code {result.returncode}\nCommand: {command}\n"
                if result.stderr:
                    error_str += f"Error: {result.stderr.strip()}\n"
                print_info(f"❌ Command failed: {result.stderr}")
                return error_str

        except subprocess.TimeoutExpired:
            error_msg = f"ERROR: Command timed out after 30s - {command}"
            print_info(f"❌ {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"ERROR: Exception executing command - {str(e)}"
            print_info(f"❌ {error_msg}")
            return error_msg
