"""
Safety checker for validating potentially destructive operations.
"""

import re
from typing import Tuple


class SafetyChecker:
    """
    Validates operations for safety and determines if user confirmation is needed.
    """

    DESTRUCTIVE_COMMANDS = [
        r"\brm\b",
        r"\bdel\b",
        r"\bformat\b",
        r"\bdd\b",
        r"\bmkfs\b",
        r"\bshred\b",
        r"\bwipe\b",
        r"\btruncate\b",
        r">\s*/dev/",
    ]

    DESTRUCTIVE_FLAGS = [
        "-rf",
        "--recursive",
        "--force",
    ]

    WINDOWS_DESTRUCTIVE_FLAGS = [
        r"\s/s\b",
        r"\s/q\b",
    ]

    PROTECTED_PATHS = [
        "/",
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/lib",
        "/proc",
        "/root",
        "/sbin",
        "/sys",
        "/usr",
        "/var",
        "C:\\Windows",
        "C:\\Program Files",
        "/System",
        "/Library",
    ]

    def is_destructive(self, command: str) -> bool:
        """
        Check if a command is potentially destructive.

        Args:
            command: Command string to check

        Returns:
            True if command is destructive
        """
        command_lower = command.lower()

        for pattern in self.DESTRUCTIVE_COMMANDS:
            if re.search(pattern, command_lower):
                return True

        for flag in self.DESTRUCTIVE_FLAGS:
            if flag in command_lower:
                return True

        for pattern in self.WINDOWS_DESTRUCTIVE_FLAGS:
            if re.search(pattern, command_lower):
                return True

        return False

    def is_protected_path(self, path: str) -> bool:
        """
        Check if a path is in a protected system directory.

        Args:
            path: File path to check

        Returns:
            True if path is protected
        """
        normalized = path.lower().rstrip("/\\")

        for protected in self.PROTECTED_PATHS:
            if normalized.startswith(protected.lower()):
                return True

        return False

    def is_protected_path_in_command(self, command: str) -> bool:
        """
        Check if command operates on a protected system path.
        Only blocks truly dangerous operations on system directories.

        Args:
            command: Shell command to check

        Returns:
            True if command targets a protected path with a destructive operation
        """
        if not self.is_destructive(command):
            return False

        for protected in self.PROTECTED_PATHS:
            if protected.lower() in command.lower():
                if re.search(r"\brm\b", command.lower()):
                    return True
                if re.search(r"\bdd\b", command.lower()):
                    return True

        return False

    def analyze_file_operation(
        self, operation: str, source: str, destination: str = None
    ) -> Tuple[bool, str]:
        """
        Analyze a file operation for safety.

        Args:
            operation: Type of operation (move, copy, delete)
            source: Source path
            destination: Destination path (for move/copy)

        Returns:
            Tuple of (is_safe, reason)
        """
        if operation == "delete":
            if self.is_protected_path(source):
                return (False, f"Cannot delete from protected path: {source}")
            return (True, "Delete operation requires confirmation")

        elif operation in ["move", "copy"]:
            if self.is_protected_path(source):
                return (False, f"Cannot {operation} from protected path: {source}")
            if destination and self.is_protected_path(destination):
                return (False, f"Cannot {operation} to protected path: {destination}")
            return (True, f"{operation.capitalize()} operation is safe")

        return (True, "Operation is safe")

    def get_confirmation_message(self, operation: str, details: str) -> str:
        """
        Generate a user-friendly confirmation message.

        Args:
            operation: Type of operation
            details: Details about what will be affected

        Returns:
            Confirmation message string
        """
        return f"""
⚠️  CONFIRMATION REQUIRED ⚠️

Operation: {operation}
Details: {details}

This operation may modify or delete data.
Do you want to proceed? (yes/no): """

    def requires_confirmation(self, command: str = None, operation: str = None) -> bool:
        """
        Determine if an operation requires user confirmation.

        Args:
            command: Shell command (optional)
            operation: Operation type (optional)

        Returns:
            True if confirmation is needed
        """
        if command and self.is_destructive(command):
            return True

        if operation in ["delete", "remove", "format"]:
            return True

        return False
