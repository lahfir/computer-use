"""
Simple element storage for accessibility elements.

Replaces the epoch-based VersionedElementRegistry with a simple dict-based store.
No epochs, no staleness tracking - elements are stored until explicitly cleared
or replaced by a new fetch.

Key design:
- Store elements in a simple dict by element_id
- Track which elements belong to which app for targeted clearing
- Generate stable, semantic element IDs based on role + label + context
- Support direct native ref clicking without staleness checks
"""

import hashlib
from typing import Dict, Any, Optional, Set


def shorten_role(role: str) -> str:
    """
    Dynamically generate short role name from ANY role string.

    Args:
        role: Any role string (e.g., "Button", "TextField")

    Returns:
        Short 3-character role identifier (e.g., "but", "tex")
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
    center: Optional[list] = None,
) -> str:
    """
    Generate stable, semantic element ID.

    ID is DETERMINISTIC: Same element -> Same ID every time.

    Args:
        role: Element role (already normalized by platform normalizer)
        label: Human-readable label (already normalized)
        identifier: Platform-specific unique ID (for collision resolution)
        app_name: Application name
        parent_path: Hash of ancestor roles for context (optional)
        center: Element center [x, y] - included in hash when label is empty

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

    if not label.strip() and center and len(center) >= 2:
        identity_parts.append(f"{center[0]}:{center[1]}")

    identity = "|".join(identity_parts)

    hash_suffix = hashlib.sha256(identity.encode()).hexdigest()[:8]

    role_short = shorten_role(role)

    label_clean = normalize_label_for_id(label, max_length=8)

    if label_clean:
        return f"e_{role_short}_{label_clean}_{hash_suffix}"
    else:
        return f"e_{role_short}_{hash_suffix}"


class SimpleElementStore:
    """
    Simple element storage. No epochs, no staleness tracking.

    Elements are stored until:
    - clear_app() is called (clears elements for a specific app)
    - clear_all() is called (clears everything)
    - A new element with the same ID is registered (updates it)

    This design allows clicking multiple elements in sequence without
    any of them becoming "stale" - just like the working test that
    clicks 53 buttons in 9 seconds.
    """

    def __init__(self):
        self._elements: Dict[str, Dict[str, Any]] = {}
        self._app_elements: Dict[str, Set[str]] = {}

    def store(self, element: Dict[str, Any], app_name: str) -> str:
        """
        Store element and return its ID.

        If an element with the same ID already exists, it's updated
        with the new data. This allows re-fetching to update element
        references without breaking existing IDs.

        Args:
            element: Normalized element dictionary with role, label, etc.
            app_name: Application name (used for app-based clearing)

        Returns:
            Stable element ID
        """
        element_id = compute_element_id(
            role=element.get("role", ""),
            label=element.get("label", ""),
            identifier=element.get("identifier", ""),
            app_name=app_name,
            parent_path=element.get("parent_path", ""),
            center=element.get("center"),
        )

        final_id = self._resolve_collision(element_id, element)

        element["element_id"] = final_id
        self._elements[final_id] = element

        app_key = app_name.lower()
        if app_key not in self._app_elements:
            self._app_elements[app_key] = set()
        self._app_elements[app_key].add(final_id)

        return final_id

    def _resolve_collision(self, computed_id: str, element: Dict[str, Any]) -> str:
        """
        Handle ID collisions by appending index or updating existing.

        If same element (same role, label, close position), update it.
        If different element, append collision index.
        """
        final_id = computed_id
        collision_index = 0

        while final_id in self._elements:
            existing = self._elements[final_id]

            if self._is_same_element(existing, element):
                return final_id

            collision_index += 1
            final_id = f"{computed_id}_{collision_index}"

        return final_id

    def _is_same_element(self, existing: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """
        Check if two element dicts represent the same UI element.

        Same if: close position (within 10px) AND same role AND same label.
        If positions can't be compared, elements are considered different.
        """
        if existing.get("role") != new.get("role"):
            return False
        if existing.get("label") != new.get("label"):
            return False

        old_center = existing.get("center")
        new_center = new.get("center")

        if not old_center or not new_center:
            return False
        if len(old_center) < 2 or len(new_center) < 2:
            return False

        dx = abs(old_center[0] - new_center[0])
        dy = abs(old_center[1] - new_center[1])
        return dx <= 10 and dy <= 10

    def get(self, element_id: str) -> Optional[Dict[str, Any]]:
        """
        Get element by ID. Returns None if not found.

        No staleness check - if it's in the store, it's usable.

        Args:
            element_id: Element ID to look up

        Returns:
            Element dictionary or None if not found
        """
        return self._elements.get(element_id)

    def clear_app(self, app_name: str) -> int:
        """
        Clear elements for a specific app before re-fetch.

        Call this before get_elements() to ensure fresh data.

        Args:
            app_name: Application name to clear

        Returns:
            Number of elements cleared
        """
        app_key = app_name.lower()
        element_ids = self._app_elements.pop(app_key, set())

        for eid in element_ids:
            self._elements.pop(eid, None)

        return len(element_ids)

    def clear_all(self) -> None:
        """Clear all elements from all apps."""
        self._elements.clear()
        self._app_elements.clear()

    def get_app_elements(self, app_name: str) -> list[Dict[str, Any]]:
        """
        Get all elements for a specific app.

        Args:
            app_name: Application name

        Returns:
            List of element dictionaries
        """
        app_key = app_name.lower()
        element_ids = self._app_elements.get(app_key, set())
        return [self._elements[eid] for eid in element_ids if eid in self._elements]

    @property
    def count(self) -> int:
        """Total number of stored elements."""
        return len(self._elements)

    def search(
        self,
        query: str,
        role_filter: Optional[str] = None,
        app_name: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """
        Search elements by label or identifier.

        Args:
            query: Search query (case-insensitive partial match)
            role_filter: Optional role to filter by
            app_name: Optional app to limit search to

        Returns:
            List of matching element dictionaries
        """
        query_lower = query.lower()
        results = []

        if app_name:
            elements = self.get_app_elements(app_name)
        else:
            elements = list(self._elements.values())

        for elem in elements:
            label = (elem.get("label") or "").lower()
            identifier = (elem.get("identifier") or "").lower()
            role = elem.get("role", "")

            if role_filter and role_filter.lower() not in role.lower():
                continue

            if query_lower in label or query_lower in identifier:
                results.append(elem)

        return results
