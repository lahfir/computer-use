"""
Platform-specific helper utilities.
"""

import platform
import subprocess
from typing import List, Dict, Optional
from pathlib import Path


class PlatformHelper:
    """
    Helper utilities for platform-specific operations.
    """

    def __init__(self):
        self.os_type = platform.system().lower()

    def get_app_launch_command(self, app_name: str) -> List[str]:
        """
        Get platform-specific command to launch an application.

        Args:
            app_name: Name of the application to launch

        Returns:
            Command as list of strings
        """
        if self.os_type == "darwin":
            return ["open", "-a", app_name]
        elif self.os_type == "windows":
            return ["start", "", app_name]
        else:
            return [app_name.lower()]

    def normalize_path(self, path: str) -> str:
        """
        Normalize path for current platform.

        Args:
            path: Path to normalize

        Returns:
            Platform-normalized path
        """
        path_obj = Path(path).expanduser()
        return str(path_obj.resolve())

    def get_keyboard_shortcut(self, action: str) -> List[str]:
        """
        Get platform-specific keyboard shortcut.

        Args:
            action: Action name (copy, paste, select_all, etc.)

        Returns:
            List of keys for the shortcut
        """
        shortcuts = self._get_shortcut_mappings()
        return shortcuts.get(action, [])

    def _get_shortcut_mappings(self) -> Dict[str, List[str]]:
        """
        Get keyboard shortcut mappings for current platform.
        """
        if self.os_type == "darwin":
            return {
                "copy": ["command", "c"],
                "paste": ["command", "v"],
                "cut": ["command", "x"],
                "select_all": ["command", "a"],
                "save": ["command", "s"],
                "quit": ["command", "q"],
                "new": ["command", "n"],
                "find": ["command", "f"],
            }
        else:
            return {
                "copy": ["ctrl", "c"],
                "paste": ["ctrl", "v"],
                "cut": ["ctrl", "x"],
                "select_all": ["ctrl", "a"],
                "save": ["ctrl", "s"],
                "quit": ["alt", "f4"],
                "new": ["ctrl", "n"],
                "find": ["ctrl", "f"],
            }

    def scale_coordinates(
        self, x: int, y: int, scaling_factor: float
    ) -> tuple[int, int]:
        """
        Scale coordinates based on display scaling.

        Args:
            x: X coordinate
            y: Y coordinate
            scaling_factor: Display scaling factor

        Returns:
            Scaled coordinates as (x, y)
        """
        if scaling_factor == 1.0:
            return (x, y)
        return (int(x * scaling_factor), int(y * scaling_factor))

    def get_default_download_path(self) -> str:
        """
        Get default download directory for current platform.

        Returns:
            Path to downloads directory
        """
        home = Path.home()

        if self.os_type == "darwin":
            downloads = home / "Downloads"
        elif self.os_type == "windows":
            downloads = home / "Downloads"
        else:
            downloads = home / "Downloads"
            if not downloads.exists():
                downloads = home

        return str(downloads)

    def execute_command(
        self,
        command: List[str],
        working_dir: Optional[str] = None,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Execute a platform-appropriate command.

        Args:
            command: Command as list of strings
            working_dir: Working directory for command execution
            capture_output: Whether to capture stdout/stderr

        Returns:
            CompletedProcess with result
        """
        if self.os_type == "windows":
            shell = True
        else:
            shell = False

        return subprocess.run(
            command,
            shell=shell,
            cwd=working_dir,
            capture_output=capture_output,
            text=True,
        )
