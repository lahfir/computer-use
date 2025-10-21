"""
Command confirmation system for user approval of shell commands.
"""

from typing import Set


class CommandConfirmation:
    """
    Manages user confirmation for shell commands.
    Tracks session-approved commands to avoid repeated prompts.
    """

    def __init__(self):
        """
        Initialize confirmation system with empty session cache.
        """
        self.session_allowed: Set[str] = set()
        self.denied = False

    def request_confirmation(self, command: str) -> tuple[bool, str]:
        """
        Request user confirmation for a shell command.

        Args:
            command: Shell command to execute

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        if self.denied:
            return False, "Agent stopped by user"

        if command in self.session_allowed:
            return True, "session_approved"

        from .ui import print_command_approval, print_success, print_failure

        while True:
            try:
                choice = print_command_approval(command)

                if choice == "1":
                    return True, "once"
                elif choice == "2":
                    self.session_allowed.add(command)
                    print_success("Command approved for session")
                    return True, "session"
                elif choice == "3":
                    self.denied = True
                    print_failure("Agent stopped by user")
                    return False, "denied"
                else:
                    from .ui import console

                    console.print("[red]Invalid choice. Please enter 1, 2, or 3.[/red]")
            except (EOFError, KeyboardInterrupt):
                self.denied = True
                return False, "interrupted"

    def is_denied(self) -> bool:
        """
        Check if user has denied execution.

        Returns:
            True if user denied execution
        """
        return self.denied

    def reset(self):
        """
        Reset session state (for testing or new session).
        """
        self.session_allowed.clear()
        self.denied = False
