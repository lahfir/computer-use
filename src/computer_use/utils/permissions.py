"""
Cross-platform permission checker and manager.
Ensures all required permissions are granted before running automation.
"""

import platform
import subprocess
from typing import Dict, List
from .ui import console
from rich.panel import Panel
from rich.table import Table
from rich import box


class PermissionStatus:
    """
    Permission status constants.
    """

    GRANTED = "granted"
    DENIED = "denied"
    NOT_DETERMINED = "not_determined"
    UNKNOWN = "unknown"


class PermissionChecker:
    """
    Cross-platform permission checker for automation tools.
    Checks and guides users to grant required permissions.
    """

    def __init__(self):
        """
        Initialize permission checker.
        """
        self.os_type = platform.system().lower()
        self.required_permissions = self._get_required_permissions()

    def _get_required_permissions(self) -> List[str]:
        """
        Get list of required permissions based on platform.

        Returns:
            List of permission names
        """
        if self.os_type == "darwin":
            return ["accessibility", "screen_recording", "automation"]
        elif self.os_type == "windows":
            return ["uiautomation"]
        elif self.os_type == "linux":
            return ["at_spi"]
        return []

    def check_all_permissions(self) -> Dict[str, str]:
        """
        Check all required permissions.

        Returns:
            Dictionary mapping permission name to status
        """
        results = {}

        if self.os_type == "darwin":
            results["accessibility"] = self._check_macos_accessibility()
            results["screen_recording"] = self._check_macos_screen_recording()
            results["automation"] = self._check_macos_automation()
        elif self.os_type == "windows":
            results["uiautomation"] = self._check_windows_uiautomation()
        elif self.os_type == "linux":
            results["at_spi"] = self._check_linux_atspi()

        return results

    def _check_macos_accessibility(self) -> str:
        """
        Check macOS Accessibility permission.

        Returns:
            Permission status
        """
        try:
            script = """
            tell application "System Events"
                return true
            end tell
            """
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return PermissionStatus.GRANTED

            if "not allowed" in result.stderr.lower():
                return PermissionStatus.DENIED

            return PermissionStatus.NOT_DETERMINED

        except Exception:
            return PermissionStatus.UNKNOWN

    def _check_macos_screen_recording(self) -> str:
        """
        Check macOS Screen Recording permission.

        Returns:
            Permission status
        """
        try:
            import pyautogui

            screenshot = pyautogui.screenshot(region=(0, 0, 1, 1))

            if screenshot.getpixel((0, 0)) == (0, 0, 0):
                return PermissionStatus.NOT_DETERMINED
            return PermissionStatus.GRANTED

        except Exception:
            return PermissionStatus.UNKNOWN

    def _check_macos_automation(self) -> str:
        """
        Check macOS Automation permission.

        Returns:
            Permission status
        """
        try:
            script = """
            tell application "Finder"
                return name
            end tell
            """
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return PermissionStatus.GRANTED

            if "not allowed" in result.stderr.lower():
                return PermissionStatus.DENIED

            return PermissionStatus.NOT_DETERMINED

        except Exception:
            return PermissionStatus.UNKNOWN

    def _check_windows_uiautomation(self) -> str:
        """
        Check Windows UI Automation availability.

        Returns:
            Permission status
        """
        try:
            import comtypes.client

            return PermissionStatus.GRANTED
        except ImportError:
            return PermissionStatus.DENIED
        except Exception:
            return PermissionStatus.UNKNOWN

    def _check_linux_atspi(self) -> str:
        """
        Check Linux AT-SPI availability.

        Returns:
            Permission status
        """
        try:
            result = subprocess.run(
                [
                    "gsettings",
                    "get",
                    "org.gnome.desktop.interface",
                    "toolkit-accessibility",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and "true" in result.stdout.lower():
                return PermissionStatus.GRANTED

            return PermissionStatus.DENIED

        except Exception:
            return PermissionStatus.UNKNOWN

    def open_permission_settings(self, permission: str) -> None:
        """
        Open system settings for specific permission.

        Args:
            permission: Permission name to open settings for
        """
        if self.os_type == "darwin":
            self._open_macos_settings(permission)
        elif self.os_type == "windows":
            self._open_windows_settings(permission)
        elif self.os_type == "linux":
            self._open_linux_settings(permission)

    def _open_macos_settings(self, permission: str) -> None:
        """
        Open macOS System Settings for specific permission.

        Args:
            permission: Permission name
        """
        pane_map = {
            "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
        }

        url = pane_map.get(permission)
        if url:
            subprocess.run(["open", url], check=False)

    def _open_windows_settings(self, permission: str) -> None:
        """
        Open Windows Settings.

        Args:
            permission: Permission name
        """
        subprocess.run(["start", "ms-settings:privacy"], shell=True, check=False)

    def _open_linux_settings(self, permission: str) -> None:
        """
        Open Linux accessibility settings.

        Args:
            permission: Permission name
        """
        try:
            subprocess.run(["gnome-control-center", "universal-access"], check=False)
        except FileNotFoundError:
            subprocess.run(["unity-control-center", "universal-access"], check=False)

    def display_permission_status(self, results: Dict[str, str]) -> None:
        """
        Display permission status in beautiful UI.

        Args:
            results: Dictionary of permission statuses
        """
        table = Table(
            title="🔐 System Permissions",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("Permission", style="cyan", width=20)
        table.add_column("Status", width=15)
        table.add_column("Required", style="yellow", width=10)

        permission_names = {
            "accessibility": "Accessibility",
            "screen_recording": "Screen Recording",
            "automation": "Automation",
            "uiautomation": "UI Automation",
            "at_spi": "AT-SPI",
        }

        for permission, status in results.items():
            name = permission_names.get(permission, permission)

            if status == PermissionStatus.GRANTED:
                status_text = "[green]✅ Granted[/green]"
            elif status == PermissionStatus.DENIED:
                status_text = "[red]❌ Denied[/red]"
            elif status == PermissionStatus.NOT_DETERMINED:
                status_text = "[yellow]⚠️  Not Set[/yellow]"
            else:
                status_text = "[dim]❓ Unknown[/dim]"

            table.add_row(name, status_text, "Yes")

        console.print()
        console.print(table)
        console.print()

    def get_missing_permissions(self, results: Dict[str, str]) -> List[str]:
        """
        Get list of permissions that are not granted.

        Args:
            results: Dictionary of permission statuses

        Returns:
            List of missing permission names
        """
        return [
            perm
            for perm, status in results.items()
            if status != PermissionStatus.GRANTED
        ]

    def guide_user_to_grant_permissions(self, missing_permissions: List[str]) -> bool:
        """
        Guide user to grant missing permissions.

        Args:
            missing_permissions: List of missing permission names

        Returns:
            True if user claims to have granted permissions, False if cancelled
        """
        if not missing_permissions:
            return True

        console.print()
        panel_content = self._get_permission_instructions(missing_permissions)

        panel = Panel(
            panel_content,
            title="[bold red]⚠️  Missing Permissions[/bold red]",
            border_style="red",
            box=box.DOUBLE,
        )

        console.print(panel)
        console.print()

        console.print("[bold cyan]What would you like to do?[/bold cyan]")
        console.print("  [1] Open System Settings (I'll grant permissions)")
        console.print("  [2] Skip permission check (may cause errors)")
        console.print("  [3] Exit")
        console.print()

        try:
            choice = console.input(
                "[bold cyan]Your choice (1/2/3):[/bold cyan] "
            ).strip()

            if choice == "1":
                console.print()
                console.print("[cyan]📂 Opening System Settings...[/cyan]")

                for perm in missing_permissions:
                    self.open_permission_settings(perm)

                console.print()
                console.print(
                    "[yellow]Please grant the required permissions in System Settings.[/yellow]"
                )
                console.print(
                    "[dim]Note: You may need to restart this program after granting permissions.[/dim]"
                )
                console.print()

                wait = console.input(
                    "[bold cyan]Press Enter after granting permissions...[/bold cyan] "
                )
                return True

            elif choice == "2":
                console.print()
                console.print(
                    "[yellow]⚠️  Continuing without permissions. Some features may not work.[/yellow]"
                )
                console.print()
                return True

            elif choice == "3":
                console.print()
                console.print(
                    "[cyan]👋 Exiting. Please grant permissions and try again.[/cyan]"
                )
                return False

            else:
                console.print("[red]Invalid choice. Exiting.[/red]")
                return False

        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Interrupted. Exiting.[/yellow]")
            return False

    def _get_permission_instructions(self, missing_permissions: List[str]) -> str:
        """
        Get platform-specific instructions for granting permissions.

        Args:
            missing_permissions: List of missing permission names

        Returns:
            Instruction text
        """
        if self.os_type == "darwin":
            return self._get_macos_instructions(missing_permissions)
        elif self.os_type == "windows":
            return self._get_windows_instructions(missing_permissions)
        elif self.os_type == "linux":
            return self._get_linux_instructions(missing_permissions)
        return "Please grant the required permissions in your system settings."

    def _get_macos_instructions(self, missing_permissions: List[str]) -> str:
        """
        Get macOS-specific permission instructions.

        Args:
            missing_permissions: List of missing permission names

        Returns:
            Instruction text
        """
        instructions = "This program needs the following permissions to work:\n\n"

        if "accessibility" in missing_permissions:
            instructions += "🔹 [bold]Accessibility[/bold]\n"
            instructions += "   Allows: Control GUI elements (click, type, etc.)\n"
            instructions += (
                "   Location: System Settings → Privacy & Security → Accessibility\n\n"
            )

        if "screen_recording" in missing_permissions:
            instructions += "🔹 [bold]Screen Recording[/bold]\n"
            instructions += "   Allows: Capture screenshots for automation\n"
            instructions += "   Location: System Settings → Privacy & Security → Screen Recording\n\n"

        if "automation" in missing_permissions:
            instructions += "🔹 [bold]Automation[/bold]\n"
            instructions += "   Allows: Control other applications (Finder, etc.)\n"
            instructions += (
                "   Location: System Settings → Privacy & Security → Automation\n\n"
            )

        instructions += "[yellow]⚡ After granting permissions, you may need to restart this program.[/yellow]"

        return instructions

    def _get_windows_instructions(self, missing_permissions: List[str]) -> str:
        """
        Get Windows-specific permission instructions.

        Args:
            missing_permissions: List of missing permission names

        Returns:
            Instruction text
        """
        instructions = "This program needs UI Automation permissions.\n\n"
        instructions += "Please ensure:\n"
        instructions += "  • Windows UI Automation is enabled\n"
        instructions += "  • Your antivirus isn't blocking automation\n"
        instructions += "  • Run as Administrator if needed\n"

        return instructions

    def _get_linux_instructions(self, missing_permissions: List[str]) -> str:
        """
        Get Linux-specific permission instructions.

        Args:
            missing_permissions: List of missing permission names

        Returns:
            Instruction text
        """
        instructions = "This program needs AT-SPI (Assistive Technology) enabled.\n\n"
        instructions += "To enable:\n"
        instructions += "  • GNOME: Settings → Universal Access → Enable\n"
        instructions += "  • Or run: gsettings set org.gnome.desktop.interface toolkit-accessibility true\n"

        return instructions


def check_and_request_permissions() -> bool:
    """
    Check all permissions and guide user to grant missing ones.

    Returns:
        True if all permissions granted or user chose to continue, False if user cancelled
    """
    checker = PermissionChecker()

    console.print()
    console.print("[bold cyan]🔐 Checking System Permissions...[/bold cyan]")
    console.print()

    results = checker.check_all_permissions()
    checker.display_permission_status(results)

    missing = checker.get_missing_permissions(results)

    if not missing:
        console.print("[green]✅ All permissions granted![/green]")
        console.print()
        return True

    return checker.guide_user_to_grant_permissions(missing)
