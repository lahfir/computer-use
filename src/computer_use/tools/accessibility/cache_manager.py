"""
Smart event-based caching for accessibility elements.

This module is PLATFORM-AGNOSTIC. It contains ZERO references to:
- macOS: No "AX" prefix, no AppKit, no atomacos
- Windows: No "UIA", no pywinauto
- Linux: No "AT-SPI", no pyatspi

Manages cache TTLs based on interaction events rather than fixed timeouts.
After actions that likely change UI state, use shorter TTLs.
"""

import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple


@dataclass
class CacheEntry:
    """Single cache entry with timestamp."""

    timestamp: float
    data: List[Dict[str, Any]]


class AccessibilityCacheManager:
    """
    Smart cache manager for accessibility elements.

    TTL strategy:
    - Default: 10s for normal observation
    - Post-interaction: 2s short TTL
    - After successful action: Advance epoch in registry
    """

    DEFAULT_TTL: float = 10.0
    POST_INTERACTION_TTL: float = 2.0

    def __init__(self):
        self._element_cache: Dict[str, CacheEntry] = {}
        self._app_cache: Dict[str, Any] = {}
        self._current_ttl: float = self.DEFAULT_TTL
        self._last_interaction_time: float = 0

    def get_elements(
        self, cache_key: str
    ) -> Optional[Tuple[float, List[Dict[str, Any]]]]:
        """
        Get cached elements if valid.

        Args:
            cache_key: Cache key (usually app_name:interactive_only)

        Returns:
            Tuple of (timestamp, elements) if cache hit, None if miss/expired
        """
        if cache_key not in self._element_cache:
            return None

        entry = self._element_cache[cache_key]
        age = time.time() - entry.timestamp

        if age > self._current_ttl:
            del self._element_cache[cache_key]
            return None

        return (entry.timestamp, entry.data)

    def set_elements(self, cache_key: str, elements: List[Dict[str, Any]]) -> None:
        """
        Cache elements.

        Args:
            cache_key: Cache key
            elements: Elements to cache
        """
        self._element_cache[cache_key] = CacheEntry(
            timestamp=time.time(),
            data=elements,
        )

    def get_app(self, app_name: str) -> Optional[Any]:
        """Get cached app reference."""
        return self._app_cache.get(app_name.lower())

    def set_app(self, app_name: str, app_ref: Any) -> None:
        """Cache app reference."""
        self._app_cache[app_name.lower()] = app_ref

    def invalidate_app(self, app_name: str) -> None:
        """Remove app from cache."""
        self._app_cache.pop(app_name.lower(), None)

    def on_interaction(self, app_name: Optional[str] = None) -> None:
        """
        Called after user interactions (click, type).

        Sets short TTL for next cache read and clears relevant caches.

        Args:
            app_name: App that was interacted with (or None for all)
        """
        self._last_interaction_time = time.time()
        self._current_ttl = self.POST_INTERACTION_TTL

        if app_name:
            prefix = app_name.lower()
            keys_to_remove = [k for k in self._element_cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._element_cache[key]
        else:
            self._element_cache.clear()

    def reset_ttl(self) -> None:
        """Reset TTL to default (called after successful observation)."""
        time_since_interaction = time.time() - self._last_interaction_time
        if time_since_interaction > self.POST_INTERACTION_TTL:
            self._current_ttl = self.DEFAULT_TTL

    def clear_all(self) -> None:
        """Clear all caches."""
        self._element_cache.clear()
        self._app_cache.clear()
        self._current_ttl = self.DEFAULT_TTL

    def invalidate(self, app_name: Optional[str] = None) -> None:
        """
        Invalidate caches for an app or all apps.

        Args:
            app_name: Specific app to invalidate, or None for all
        """
        if app_name:
            self.on_interaction(app_name)
        else:
            self.clear_all()

    @property
    def current_ttl(self) -> float:
        """Get current TTL value."""
        return self._current_ttl
