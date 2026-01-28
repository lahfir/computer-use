"""
Versioned element registry for stable element ID management.

This module is PLATFORM-AGNOSTIC. It contains ZERO references to:
- macOS: No "AX" prefix, no "AXButton", no AppKit, no atomacos
- Windows: No "UIA", no pywinauto, no "Edit" (Windows-specific name)
- Linux: No "AT-SPI", no pyatspi, no "push button" (Linux-specific name)

All platform-specific normalization happens in platform normalizers BEFORE
data reaches this registry. This registry only works with normalized data.

Key improvements:
1. Semantic IDs based on element identity (role + label + context), not position
2. Epoch-based versioning - marks elements stale instead of deleting
3. Dynamic role shortening - NO HARDCODED DICTIONARIES
4. Collision handling for elements with same semantic identity
"""

import hashlib
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List


def shorten_role(role: str) -> str:
    """
    Dynamically generate short role name from ANY role string.

    NO HARDCODED MAPPINGS. Works with ANY role - known or unknown.
    This function handles roles that don't exist yet or custom roles.

    Args:
        role: Any role string (e.g., "Button", "CustomWidget", "FutureRole2030")

    Returns:
        Short 3-character role identifier (e.g., "but", "cus", "fut")
    """
    if not role:
        return "unk"

    clean = role.lower().strip()
    if not clean:
        return "unk"

    return clean[:3] if len(clean) >= 3 else clean


def normalize_label_for_id(label: str, max_length: int = 20) -> str:
    """
    Normalize label for use in element ID generation.

    Args:
        label: Raw label string
        max_length: Maximum length of normalized label

    Returns:
        Cleaned label suitable for ID (alphanumeric + underscores only)
    """
    if not label:
        return ""

    normalized = label.lower().strip()
    normalized = "".join(c if c.isalnum() else "_" for c in normalized)
    normalized = "_".join(part for part in normalized.split("_") if part)

    return normalized[:max_length]


def compute_element_id(
    role: str,
    label: str,
    identifier: str,
    app_name: str,
    parent_path: str = "",
) -> str:
    """
    Generate stable, semantic element ID.

    CRITICAL: Uses ONLY platform-agnostic normalized data.
    The platform normalizer has ALREADY:
    - Stripped AX prefix (macOS)
    - Mapped Edit→TextField (Windows)
    - Converted "push button"→Button (Linux)

    ID is DETERMINISTIC: Same element → Same ID every time.

    Args:
        role: Element role (already normalized by platform normalizer)
        label: Human-readable label (already normalized)
        identifier: Platform-specific unique ID (for collision resolution)
        app_name: Application name
        parent_path: Hash of ancestor roles for context (optional)

    Returns:
        Stable element ID like "e_but_save_a1b2c3d4"
    """
    identity_parts = [
        app_name.lower().strip(),
        role.lower().strip(),
        label.lower().strip()[:50],
        identifier.strip(),
        parent_path.strip(),
    ]
    identity = "|".join(identity_parts)

    hash_suffix = hashlib.sha256(identity.encode()).hexdigest()[:8]

    role_short = shorten_role(role)

    label_clean = normalize_label_for_id(label, max_length=8)

    if label_clean:
        return f"e_{role_short}_{label_clean}_{hash_suffix}"
    else:
        return f"e_{role_short}_{hash_suffix}"


@dataclass
class ElementRecord:
    """Record for a registered element."""

    element_id: str
    element_info: Dict[str, Any]
    native_ref: Any
    registered_epoch: int
    last_seen_epoch: int
    is_stale: bool = False


class VersionedElementRegistry:
    """
    Platform-agnostic element registry with epoch-based versioning.

    Receives ONLY normalized data. Has ZERO knowledge of:
    - macOS AX APIs
    - Windows UIA
    - Linux AT-SPI

    Instead of clearing the registry after each interaction, we advance an epoch
    and mark elements stale if they're not seen in subsequent refreshes. This
    allows stale element IDs to return helpful error messages instead of "not found".
    """

    def __init__(self, max_stale_epochs: int = 5):
        """
        Initialize the registry.

        Args:
            max_stale_epochs: Number of epochs before element considered definitely stale
        """
        self._registry: Dict[str, ElementRecord] = {}
        self._current_epoch: int = 0
        self._max_stale_epochs: int = max_stale_epochs

    @property
    def current_epoch(self) -> int:
        """Get current epoch number."""
        return self._current_epoch

    def advance_epoch(self, reason: str = "interaction") -> int:
        """
        Advance epoch after interactions. Does NOT clear registry.

        Args:
            reason: Why the epoch is advancing (for logging/debugging)

        Returns:
            New epoch number
        """
        self._current_epoch += 1
        self._prune_old_entries()
        return self._current_epoch

    def _prune_old_entries(self) -> None:
        """Remove entries that have been stale for too long."""
        to_remove = []
        for eid, record in self._registry.items():
            if record.is_stale:
                age = self._current_epoch - record.last_seen_epoch
                if age > self._max_stale_epochs * 2:
                    to_remove.append(eid)

        for eid in to_remove:
            del self._registry[eid]

    def _is_same_element(self, existing: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """
        Check if two element dicts represent the same UI element.

        Same if: close position (within 50px) AND same role AND same label.

        Args:
            existing: Existing element info dict
            new: New element info dict

        Returns:
            True if they represent the same element
        """
        if existing.get("role") != new.get("role"):
            return False
        if existing.get("label") != new.get("label"):
            return False

        old_center = existing.get("center", [0, 0])
        new_center = new.get("center", [0, 0])

        if old_center and new_center and len(old_center) >= 2 and len(new_center) >= 2:
            dx = abs(old_center[0] - new_center[0])
            dy = abs(old_center[1] - new_center[1])
            return dx <= 50 and dy <= 50

        return True

    def _resolve_collision(self, computed_id: str, element_info: Dict[str, Any]) -> str:
        """
        Handle ID collisions by appending index.

        If e_but_save_a1b2c3d4 already exists:
        - Check if it's the SAME element (update it)
        - If different element, use e_but_save_a1b2c3d4_1, then _2, etc.

        Args:
            computed_id: Pre-computed semantic ID
            element_info: Element data dictionary

        Returns:
            Final element ID (may have collision index appended)
        """
        final_id = computed_id
        collision_index = 0

        while final_id in self._registry:
            existing = self._registry[final_id]

            if self._is_same_element(existing.element_info, element_info):
                existing.element_info = element_info
                existing.native_ref = element_info.get("_native_ref")
                existing.last_seen_epoch = self._current_epoch
                existing.is_stale = False
                return final_id

            collision_index += 1
            final_id = f"{computed_id}_{collision_index}"

        return final_id

    def register_element(self, normalized_element: Dict[str, Any]) -> str:
        """
        Register a normalized element.

        Args:
            normalized_element: Must match NormalizedElement schema:
                - role: str (platform-normalized)
                - label: str
                - identifier: str
                - app_name: str
                - center: [int, int]
                - bounds: [int, int, int, int]
                - has_actions: bool
                - enabled: bool
                - focused: bool
                - _native_ref: Any (opaque to registry)
                - parent_path: str (optional)

        Returns:
            Stable element ID
        """
        element_id = compute_element_id(
            role=normalized_element.get("role", ""),
            label=normalized_element.get("label", ""),
            identifier=normalized_element.get("identifier", ""),
            app_name=normalized_element.get("app_name", ""),
            parent_path=normalized_element.get("parent_path", ""),
        )

        final_id = self._resolve_collision(element_id, normalized_element)

        if final_id not in self._registry:
            self._registry[final_id] = ElementRecord(
                element_id=final_id,
                element_info=normalized_element,
                native_ref=normalized_element.get("_native_ref"),
                registered_epoch=self._current_epoch,
                last_seen_epoch=self._current_epoch,
                is_stale=False,
            )

        return final_id

    def get_element(self, element_id: str) -> Tuple[Optional[ElementRecord], str]:
        """
        Get element with staleness status.

        Args:
            element_id: Element ID to look up

        Returns:
            Tuple of (record, status) where status is:
            - "valid": Element exists and is current
            - "stale": Element exists but may be outdated
            - "not_found": Element not in registry
        """
        if element_id not in self._registry:
            return (None, "not_found")

        record = self._registry[element_id]

        if record.is_stale:
            return (record, "stale")

        epoch_age = self._current_epoch - record.last_seen_epoch
        if epoch_age > self._max_stale_epochs:
            return (record, "stale")

        return (record, "valid")

    def refresh_elements(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update registry with fresh elements. Mark unseen as stale.

        Args:
            elements: List of normalized element info dictionaries

        Returns:
            Stats dict with matched, new, and stale counts
        """
        seen_ids = set()
        stats = {"matched": 0, "new": 0, "stale": []}

        for elem_info in elements:
            eid = self.register_element(elem_info)
            seen_ids.add(eid)

            record = self._registry.get(eid)
            if record and record.registered_epoch < self._current_epoch:
                stats["matched"] += 1
            else:
                stats["new"] += 1

        for eid, record in self._registry.items():
            if eid not in seen_ids and not record.is_stale:
                record.is_stale = True
                stats["stale"].append(eid)

        return stats

    def clear(self) -> None:
        """Clear all elements (use sparingly - prefer advance_epoch)."""
        self._registry.clear()
        self._current_epoch = 0

    def get_all_elements(self) -> Dict[str, ElementRecord]:
        """Get all registered elements (copy)."""
        return self._registry.copy()

    def get_valid_elements(self) -> List[ElementRecord]:
        """Get all non-stale elements."""
        return [
            record
            for record in self._registry.values()
            if not record.is_stale
            and (self._current_epoch - record.last_seen_epoch) <= self._max_stale_epochs
        ]

    def search_elements(
        self,
        query: str,
        role_filter: Optional[str] = None,
        include_stale: bool = False,
    ) -> List[ElementRecord]:
        """
        Search elements by label or identifier.

        Args:
            query: Search query (case-insensitive partial match)
            role_filter: Optional role to filter by
            include_stale: Whether to include stale elements

        Returns:
            List of matching ElementRecords
        """
        query_lower = query.lower()
        results = []

        for record in self._registry.values():
            if not include_stale and record.is_stale:
                continue

            if not include_stale:
                epoch_age = self._current_epoch - record.last_seen_epoch
                if epoch_age > self._max_stale_epochs:
                    continue

            info = record.element_info
            label = (info.get("label") or "").lower()
            identifier = (info.get("identifier") or "").lower()
            role = info.get("role", "")

            if role_filter and role_filter.lower() not in role.lower():
                continue

            if query_lower in label or query_lower in identifier:
                results.append(record)

        return results
