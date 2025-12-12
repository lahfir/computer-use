"""
Cross-platform process management tool.
"""

import psutil
import subprocess
import platform
from typing import List, Dict, Optional


class ProcessTool:
    """
    Process management for listing, launching, and closing applications.
    """

    def __init__(self):
        self.os_type = platform.system().lower()

    def list_running_processes(self) -> List[Dict[str, any]]:
        """
        Get list of currently running processes.

        Returns:
            List of process dictionaries with name, pid, and status
        """
        processes = []

        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                processes.append(
                    {
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "status": proc.info["status"],
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return processes

    def find_process_by_name(self, name: str) -> List[Dict[str, any]]:
        """
        Find processes matching a name.

        Args:
            name: Process name to search for (partial match)

        Returns:
            List of matching processes
        """
        name_lower = name.lower()
        matching = []

        for proc in self.list_running_processes():
            if name_lower in proc["name"].lower():
                matching.append(proc)

        return matching

    def is_process_running(self, name: str) -> bool:
        """
        Check if a process with given name is running.

        Args:
            name: Process name to check

        Returns:
            True if process is running
        """
        return len(self.find_process_by_name(name)) > 0

    def launch_app(self, app_name: str) -> bool:
        """
        Launch an application.

        Args:
            app_name: Name of application to launch

        Returns:
            True if launch command executed successfully
        """
        try:
            if self.os_type == "darwin":
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    check=True,
                )
            elif self.os_type == "windows":
                subprocess.Popen(["start", "", app_name], shell=True)
            else:
                subprocess.Popen([app_name.lower()])

            return True
        except Exception:
            return False

    def focus_app(self, app_name: str) -> bool:
        """
        Focus/activate an application window (bring to front).
        Works even if app is already running.

        Args:
            app_name: Name of application to focus

        Returns:
            True if focus command executed successfully
        """
        try:
            if self.os_type == "darwin":
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    check=True,
                    timeout=5,
                )
            elif self.os_type == "windows":
                import ctypes

                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, app_name)
                if hwnd:
                    user32.SetForegroundWindow(hwnd)
                else:
                    subprocess.Popen(["start", "", app_name], shell=True)
            else:  # Linux
                try:
                    subprocess.run(["wmctrl", "-a", app_name], check=True, timeout=5)
                except FileNotFoundError:
                    subprocess.run(
                        ["xdotool", "search", "--name", app_name, "windowactivate"],
                        timeout=5,
                    )

            return True
        except Exception:
            return False

    def open_application(self, app_name: str) -> Dict[str, any]:
        """
        Open/focus an application and bring it to front.
        Works for both launching new apps and focusing already-running apps.

        Args:
            app_name: Name of application to open/focus

        Returns:
            Dictionary with success status and message
        """
        # launch_app already includes activate, which brings to front
        success = self.launch_app(app_name)
        return {
            "success": success,
            "message": (
                f"Opened and focused {app_name}"
                if success
                else f"Failed to open {app_name}"
            ),
            "app_name": app_name,
        }

    def close_process(self, pid: int, force: bool = False) -> bool:
        """
        Close a process by PID.

        Args:
            pid: Process ID to close
            force: Whether to force kill

        Returns:
            True if process was closed
        """
        try:
            proc = psutil.Process(pid)

            if force:
                proc.kill()
            else:
                proc.terminate()

            proc.wait(timeout=5)
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
            return False

    def close_app_by_name(self, name: str, force: bool = False) -> int:
        """
        Close all processes matching a name.

        Args:
            name: Process name to close
            force: Whether to force kill

        Returns:
            Number of processes closed
        """
        processes = self.find_process_by_name(name)
        closed_count = 0

        for proc in processes:
            if self.close_process(proc["pid"], force=force):
                closed_count += 1

        return closed_count

    def get_process_info(self, pid: int) -> Optional[Dict[str, any]]:
        """
        Get detailed information about a process.

        Args:
            pid: Process ID

        Returns:
            Dictionary with process details or None if not found
        """
        try:
            proc = psutil.Process(pid)
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "status": proc.status(),
                "cpu_percent": proc.cpu_percent(),
                "memory_percent": proc.memory_percent(),
                "create_time": proc.create_time(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
