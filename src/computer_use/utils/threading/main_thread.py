"""Utilities for executing callables on the main thread event loop."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Callable, Optional

_main_loop: Optional[asyncio.AbstractEventLoop] = None
_main_thread_id: Optional[int] = None


def set_main_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Register the main event loop and thread identity."""
    global _main_loop, _main_thread_id
    _main_loop = loop
    _main_thread_id = threading.get_ident()


def is_main_thread() -> bool:
    """Return True if the current thread is the registered main thread."""
    return _main_thread_id is not None and threading.get_ident() == _main_thread_id


def run_on_main_thread(
    func: Callable[..., Any], *args: Any, timeout: Optional[float] = None, **kwargs: Any
) -> Any:
    """
    Run a callable on the main thread if a loop is registered.

    Falls back to direct execution when no loop is registered or already
    running on the main thread.
    """
    if (
        _main_loop is None
        or _main_loop.is_closed()
        or not _main_loop.is_running()
        or is_main_thread()
    ):
        return func(*args, **kwargs)

    future: Future = Future()

    def _call() -> None:
        if future.cancelled():
            return
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - passthrough
            future.set_exception(exc)
        else:
            future.set_result(result)

    try:
        _main_loop.call_soon_threadsafe(_call)
    except RuntimeError:
        return func(*args, **kwargs)

    return future.result(timeout=timeout)
