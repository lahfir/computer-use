"""
Cross-platform permission checker and manager.
Ensures all required permissions are granted before running automation.
"""

import platform
import subprocess
from typing import Dict, List, Tuple

from .ui import console, THEME


class PermissionStatus:
    """Permission status constants."""

    GRANTED = "granted"
    DENIED = "denied"
    NOT_DETERMINED = "not_determined"
    UNKNOWN = "unknown"


PERMISSION_INFO = {
    "accessibility": {
        "name": "Accessibility",
        "desc": "Control mouse, keyboard, and read UI elements",
        "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        "platform": "darwin",
    },
    "screen_recording": {
        "name": "Screen Recording",
        "desc": "Capture screenshots for visual analysis",
        "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
        "platform": "darwin",
    },
    "automation": {
        "name": "Automation",
        "desc": "Control other applications via AppleScript",
        "settings_url": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
        "platform": "darwin",
    },
    "uiautomation": {
        "name": "UI Automation",
        "desc": "Control Windows UI elements and read screen content",
        "settings_url": "ms-settings:privacy",
        "platform": "windows",
    },
    "at_spi": {
        "name": "AT-SPI",
        "desc": "Assistive Technology Service Provider Interface for automation",
        "settings_url": None,
        "settings_cmd": ["gnome-control-center", "universal-access"],
        "platform": "linux",
    },
}


class PermissionChecker:
    """Cross-platform permission checker for automation tools."""

    def __init__(self):
        """Initialize permission checker."""
        self.os_type = platform.system().lower()

    def check_all_permissions(self) -> Dict[str, str]:
        """Check all required permissions."""
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
        """Check macOS Accessibility permission."""
        try:
            script = 'tell application "System Events" to return true'
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
        """Check macOS Screen Recording permission."""
        try:
            import pyautogui

            screenshot = pyautogui.screenshot(region=(0, 0, 1, 1))
            if screenshot.getpixel((0, 0)) == (0, 0, 0):
                return PermissionStatus.NOT_DETERMINED
            return PermissionStatus.GRANTED
        except Exception:
            return PermissionStatus.UNKNOWN

    def _check_macos_automation(self) -> str:
        """Check macOS Automation permission."""
        try:
            script = 'tell application "Finder" to return name'
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
        """Check Windows UI Automation availability."""
        import importlib.util

        if importlib.util.find_spec("comtypes") is not None:
            return PermissionStatus.GRANTED
        return PermissionStatus.DENIED

    def _check_linux_atspi(self) -> str:
        """Check Linux AT-SPI availability."""
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
        """Open system settings for specific permission."""
        info = PERMISSION_INFO.get(permission, {})

        if self.os_type == "darwin":
            url = info.get("settings_url")
            if url:
                subprocess.run(["open", url], check=False)

        elif self.os_type == "windows":
            url = info.get("settings_url", "ms-settings:privacy")
            subprocess.run(["start", url], shell=True, check=False)

        elif self.os_type == "linux":
            cmd = info.get("settings_cmd")
            if cmd:
                try:
                    subprocess.run(cmd, check=False)
                except FileNotFoundError:
                    subprocess.run(
                        ["unity-control-center", "universal-access"], check=False
                    )

    def get_missing_permissions(self, results: Dict[str, str]) -> List[str]:
        """Get list of permissions that are not granted."""
        return [
            perm
            for perm, status in results.items()
            if status != PermissionStatus.GRANTED
        ]


def _format_permission_status(results: Dict[str, str]) -> str:
    """Format permission status as compact inline text."""
    parts = []
    for perm, status in results.items():
        info = PERMISSION_INFO.get(perm, {"name": perm})
        name = info["name"]
        if status == PermissionStatus.GRANTED:
            parts.append(f"{name} ✓")
        elif status == PermissionStatus.DENIED:
            parts.append(f"{name} ✗")
        else:
            parts.append(f"{name} ?")
    return "  ".join(parts)


def _prompt_missing_permissions(
    checker: PermissionChecker, missing: List[str]
) -> Tuple[bool, bool]:
    """
    Prompt user for missing permissions.
    Returns (should_continue, permissions_resolved).
    """
    console.print()

    for perm in missing:
        info = PERMISSION_INFO.get(perm, {"name": perm, "desc": "Required"})
        console.print(
            f"  [{THEME['error']}]✗[/] [{THEME['fg']}]{info['name']}[/] "
            f"[{THEME['muted']}]- {info['desc']}[/]"
        )

    console.print()
    console.print(
        f"  [{THEME['muted']}][1][/] Open Settings  "
        f"[{THEME['muted']}][2][/] Skip  "
        f"[{THEME['muted']}][3][/] Exit"
    )

    try:
        choice = console.input(f"\n  [{THEME['accent']}]›[/] ").strip()

        if choice == "1":
            for perm in missing:
                checker.open_permission_settings(perm)
            console.print(
                f"\n  [{THEME['muted']}]Grant permissions, then press Enter...[/]"
            )
            console.input()
            return True, True

        elif choice == "2":
            console.print(f"\n  [{THEME['warning']}]⚠ Limited functionality[/]")
            return True, False

        elif choice == "3":
            return False, False

        return False, False

    except (EOFError, KeyboardInterrupt):
        return False, False


def check_and_request_permissions() -> bool:
    """
    Check all permissions and guide user to grant missing ones.
    Returns True if permissions OK or user chose to continue, False if cancelled.

    This function is silent when all permissions are granted.
    """
    checker = PermissionChecker()
    results = checker.check_all_permissions()
    missing = checker.get_missing_permissions(results)

    if not missing:
        return True

    should_continue, resolved = _prompt_missing_permissions(checker, missing)

    if resolved:
        new_results = checker.check_all_permissions()
        new_missing = checker.get_missing_permissions(new_results)
        if new_missing:
            console.print(f"  [{THEME['warning']}]⚠ Some permissions still missing[/]")

    return should_continue


def get_permission_summary() -> str:
    """Get a compact permission summary string for status display."""
    checker = PermissionChecker()
    results = checker.check_all_permissions()

    all_granted = all(status == PermissionStatus.GRANTED for status in results.values())

    if all_granted:
        return "✓"
    else:
        missing = [
            PERMISSION_INFO.get(p, {"name": p})["name"]
            for p, s in results.items()
            if s != PermissionStatus.GRANTED
        ]
        return f"⚠ {', '.join(missing)}"
