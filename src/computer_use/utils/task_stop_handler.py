"""
Task stop handler for ESC key interrupt.
"""

from threading import Thread, Event
from typing import Optional
from pynput import keyboard


class TaskStopHandler:
    """
    Handles ESC key press to stop current task execution.
    """

    def __init__(self):
        """
        Initialize task stop handler.
        """
        self._stop_event = Event()
        self._listener: Optional[keyboard.Listener] = None
        self._is_running = False

    def start_listening(self):
        """
        Start listening for ESC key press.
        """
        self._stop_event.clear()
        self._is_running = True

        def on_press(key):
            """
            Handle key press events.
            """
            if key == keyboard.Key.esc and self._is_running:
                self._stop_event.set()

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.start()

    def stop_listening(self):
        """
        Stop listening for ESC key press.
        """
        self._is_running = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    def is_stopped(self) -> bool:
        """
        Check if ESC was pressed.

        Returns:
            True if ESC was pressed
        """
        return self._stop_event.is_set()

    def reset(self):
        """
        Reset the stop event for next task.
        """
        self._stop_event.clear()

    def __enter__(self):
        """
        Context manager entry.
        """
        self.start_listening()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit.
        """
        self.stop_listening()

