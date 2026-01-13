"""
System command tool for CrewAI.
Extracted from system_agent.py, rewritten for CrewAI integration.
"""

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from .instrumented_tool import InstrumentedBaseTool


class ExecuteCommandInput(BaseModel):
    """Input for executing shell command."""

    command: str = Field(description="Shell command to execute")


class ExecuteShellCommandTool(InstrumentedBaseTool):
    """Execute shell command safely with validation."""

    name: str = "execute_shell_command"
    description: str = (
        "Run shell command. SUCCESS=executed (exit 0), NOT goal achieved. "
        "Verify results with follow-up command."
    )
    args_schema: type[BaseModel] = ExecuteCommandInput

    def _extract_command(self, command: str) -> str:
        """
        Extract actual command from potentially malformed input.
        Handles JSON arrays or objects passed by CrewAI.
        """
        if not command:
            return command

        command = command.strip()

        if command.startswith("[") or command.startswith("{"):
            try:
                parsed = json.loads(command)
                if isinstance(parsed, list) and len(parsed) > 0:
                    first_item = parsed[0]
                    if isinstance(first_item, dict) and "command" in first_item:
                        return first_item["command"]
                elif isinstance(parsed, dict) and "command" in parsed:
                    return parsed["command"]
            except json.JSONDecodeError:
                pass

        return command

    def _run(self, command: str) -> str:
        """
        Execute shell command with safety checks.

        Args:
            command: Shell command to execute

        Returns:
            String result for CrewAI
        """
        from ..utils.ui import dashboard, ActionType

        if dashboard.get_current_agent_name() == "Manager":
            dashboard.set_agent("System Agent")

        command = self._extract_command(command)

        safety_checker = self._safety_checker
        confirmation_manager = self._confirmation_manager

        if safety_checker:
            if safety_checker.is_protected_path_in_command(command):
                error_msg = f"Command targets protected system path: {command}"
                dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
                return f"ERROR: {error_msg}"

        if confirmation_manager:
            dashboard._stop_live_status()
            approved, reason = confirmation_manager.request_confirmation(command)
            if not approved:
                error_msg = f"User {reason} command: {command}"
                dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
                return f"ERROR: {error_msg}"
            dashboard.reset_tool_timer("execute_shell_command")
            dashboard._start_live_status()

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
                output_str = f"SUCCESS (exit 0)\nCommand: {command}\n"
                if result.stdout:
                    stdout = result.stdout.strip()
                    line_limit = 40
                    char_limit = 2000

                    lines = stdout.split("\n")
                    original_line_count = len(lines)
                    original_char_count = len(stdout)

                    if original_line_count > line_limit:
                        output_body = "\n".join(lines[:line_limit])
                        output_str += (
                            f"Output truncated to {line_limit} lines (of {original_line_count}):\n{output_body}\n"
                            f"... [{original_line_count - line_limit} more truncated]\n"
                        )
                    elif original_char_count > char_limit:
                        output_str += (
                            f"Output truncated to {char_limit} chars (of {original_char_count}):\n"
                            f"{stdout[:char_limit]}\n...\n"
                        )
                    else:
                        output_str += f"Output:\n{stdout}\n"

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
            return (
                f"TIMEOUT: Command exceeded 30s limit.\n"
                f"Command: {command}\n"
                f"ACTION REQUIRED: Use a faster alternative:\n"
                f"- Use indexed search (mdfind/locate) instead of find\n"
                f"- Add depth limits (-maxdepth 3)\n"
                f"- Search a smaller scope (specific folder)\n"
                f"- If you already found valid results earlier, use those instead\n"
            )
        except Exception as e:
            error_msg = f"Exception executing command: {str(e)}"
            dashboard.add_log_entry(ActionType.ERROR, error_msg, status="error")
            return f"ERROR: {error_msg}"
