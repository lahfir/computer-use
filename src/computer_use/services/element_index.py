"""
Searchable element index for finding ANY element in an application.

This service enables discovery of elements beyond the top 30 displayed
by the get_accessible_elements tool. It provides fuzzy search and
filtering capabilities.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SearchResult:
    """Result from an element search."""

    element_id: str
    label: str
    role: str
    match_score: float
    match_reason: str
    element_info: Dict[str, Any]


class ElementIndex:
    """
    Searchable index for all elements in an application.

    This class stores ALL elements (not just top 30) and provides
    search capabilities for finding specific elements.
    """

    def __init__(self):
        self._elements: Dict[str, Dict[str, Any]] = {}
        self._by_role: Dict[str, List[str]] = {}
        self._by_label_words: Dict[str, List[str]] = {}

    def clear(self) -> None:
        """Clear the index."""
        self._elements.clear()
        self._by_role.clear()
        self._by_label_words.clear()

    def index_elements(self, elements: List[Dict[str, Any]]) -> int:
        """
        Index a list of elements.

        Args:
            elements: List of element dictionaries with element_id, role, label, etc.

        Returns:
            Number of elements indexed
        """
        self.clear()

        for elem in elements:
            element_id = elem.get("element_id", "")
            if not element_id:
                continue

            self._elements[element_id] = elem

            role = (elem.get("role") or "").lower()
            if role:
                if role not in self._by_role:
                    self._by_role[role] = []
                self._by_role[role].append(element_id)

            label = elem.get("label") or ""
            words = self._extract_words(label)
            for word in words:
                if word not in self._by_label_words:
                    self._by_label_words[word] = []
                self._by_label_words[word].append(element_id)

        return len(self._elements)

    def _extract_words(self, text: str) -> List[str]:
        """Extract searchable words from text."""
        if not text:
            return []

        text_lower = text.lower().strip()
        if len(text_lower) == 1:
            return [text_lower]

        words = []
        current_word = []

        for char in text_lower:
            if char.isalnum():
                current_word.append(char)
            else:
                if current_word:
                    words.append("".join(current_word))
                    current_word = []

        if current_word:
            words.append("".join(current_word))

        return words

    def search(
        self,
        query: str,
        role_filter: Optional[str] = None,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """
        Search for elements matching a query using O(1) lookups.

        Args:
            query: Search query (partial match on label)
            role_filter: Optional role to filter by
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects sorted by match score
        """
        if not query:
            return self._get_all_by_role(role_filter, max_results)

        query_lower = query.lower().strip()
        query_words = self._extract_words(query)
        results: Dict[str, SearchResult] = {}

        for word in query_words:
            element_ids = self._by_label_words.get(word)
            if element_ids:
                for eid in element_ids:
                    if eid in results:
                        continue
                    elem = self._elements.get(eid, {})
                    if role_filter:
                        elem_role = (elem.get("role") or "").lower()
                        if role_filter.lower() not in elem_role:
                            continue
                    score = self._compute_score(elem, query_lower, query_words)
                    results[eid] = SearchResult(
                        element_id=eid,
                        label=elem.get("label", ""),
                        role=elem.get("role", ""),
                        match_score=score,
                        match_reason=f"word: {word}",
                        element_info=elem,
                    )
                    if len(results) >= max_results:
                        break

        if len(results) < max_results:
            for eid, elem in self._elements.items():
                if eid in results:
                    continue

                label = (elem.get("label") or "").lower()
                identifier = (elem.get("identifier") or "").lower()

                if query_lower in label or query_lower in identifier:
                    if role_filter:
                        elem_role = (elem.get("role") or "").lower()
                        if role_filter.lower() not in elem_role:
                            continue

                    score = self._compute_score(elem, query_lower, query_words)
                    results[eid] = SearchResult(
                        element_id=eid,
                        label=elem.get("label", ""),
                        role=elem.get("role", ""),
                        match_score=score,
                        match_reason="substring match",
                        element_info=elem,
                    )

                    if len(results) >= max_results:
                        break

        return sorted(results.values(), key=lambda r: -r.match_score)[:max_results]

    def _compute_score(
        self, elem: Dict[str, Any], query_lower: str, query_words: List[str]
    ) -> float:
        """Compute match score for an element."""
        score = 0.0

        label = (elem.get("label") or "").lower()

        if label == query_lower:
            score += 100.0
        elif label.startswith(query_lower):
            score += 50.0
        elif query_lower in label:
            score += 25.0

        for word in query_words:
            if word in label:
                score += 10.0

        if elem.get("focused"):
            score += 5.0
        if elem.get("enabled"):
            score += 2.0

        return score

    def _get_all_by_role(
        self, role_filter: Optional[str], max_results: int
    ) -> List[SearchResult]:
        """Get all elements, optionally filtered by role."""
        results = []

        for eid, elem in self._elements.items():
            if role_filter:
                elem_role = (elem.get("role") or "").lower()
                if role_filter.lower() not in elem_role:
                    continue

            results.append(
                SearchResult(
                    element_id=eid,
                    label=elem.get("label", ""),
                    role=elem.get("role", ""),
                    match_score=0.0,
                    match_reason="no query",
                    element_info=elem,
                )
            )

            if len(results) >= max_results:
                break

        return results

    def get_by_id(self, element_id: str) -> Optional[Dict[str, Any]]:
        """Get element by ID."""
        return self._elements.get(element_id)

    def get_by_role(self, role: str) -> List[Dict[str, Any]]:
        """Get all elements with a specific role."""
        role_lower = role.lower()
        element_ids = self._by_role.get(role_lower, [])
        return [self._elements[eid] for eid in element_ids if eid in self._elements]

    @property
    def element_count(self) -> int:
        """Get total number of indexed elements."""
        return len(self._elements)

    def get_role_summary(self) -> Dict[str, int]:
        """Get a summary of elements by role."""
        return {role: len(ids) for role, ids in self._by_role.items()}


_global_index: Optional[ElementIndex] = None


def get_element_index() -> ElementIndex:
    """Get the global element index singleton."""
    global _global_index
    if _global_index is None:
        _global_index = ElementIndex()
    return _global_index


def search_elements(
    query: str,
    role_filter: Optional[str] = None,
    max_results: int = 20,
) -> List[SearchResult]:
    """
    Search for elements in the global index.

    Args:
        query: Search query (partial match on label)
        role_filter: Optional role to filter by
        max_results: Maximum number of results

    Returns:
        List of SearchResult objects
    """
    return get_element_index().search(query, role_filter, max_results)


def index_elements(elements: List[Dict[str, Any]]) -> int:
    """
    Index elements in the global index.

    Args:
        elements: List of element dictionaries

    Returns:
        Number of elements indexed
    """
    return get_element_index().index_elements(elements)
