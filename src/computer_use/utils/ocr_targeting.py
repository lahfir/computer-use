"""
OCR-based targeting utilities for GUI automation.
Word-boundary matching, spatial scoring, and candidate ranking.
"""

import re
from typing import Optional, List, Any


def is_word_boundary_match(text: str, target: str) -> bool:
    """
    Check if target appears at word boundaries in text.

    Args:
        text: Text to search in
        target: Target word to find

    Returns:
        True if target is a whole word in text
    """
    pattern = r"\b" + re.escape(target) + r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def determine_text_relation(text_lower: str, target_lower: str) -> str:
    """
    Determine the relation between text and target.

    Args:
        text_lower: Text in lowercase
        target_lower: Target in lowercase

    Returns:
        Relation type: exact, prefix, word, substring, partial, none
    """
    if text_lower == target_lower:
        return "exact"
    if text_lower.startswith(target_lower):
        return "prefix"
    if target_lower in text_lower:
        if is_word_boundary_match(text_lower, target_lower):
            return "word"
        return "substring"
    if target_lower.startswith(text_lower) and len(text_lower) >= 3:
        return "partial"
    return "none"


def compute_spatial_score(
    center_x: float,
    center_y: float,
    screenshot_width: int,
    screenshot_height: int,
    visual_context: Optional[str] = None,
) -> float:
    """
    Compute spatial position penalty based on visual context.

    Args:
        center_x: X coordinate of element center
        center_y: Y coordinate of element center
        screenshot_width: Width of screenshot
        screenshot_height: Height of screenshot
        visual_context: Spatial context keywords (e.g., "top left", "right side")

    Returns:
        Position penalty (lower is better, 0 = perfect match)
    """
    norm_y = center_y / max(screenshot_height, 1)
    norm_x = center_x / max(screenshot_width, 1)

    if not visual_context:
        return center_y * 0.05 + center_x * 0.01

    context_lower = visual_context.lower()
    penalty = 0.0

    # Vertical positioning
    if "top" in context_lower or "upper" in context_lower:
        penalty += norm_y * 600
    elif "bottom" in context_lower or "lower" in context_lower:
        penalty += (1 - norm_y) * 600
    elif "middle" in context_lower or "center" in context_lower:
        penalty += abs(norm_y - 0.5) * 400

    # Horizontal positioning
    if "left" in context_lower:
        penalty += norm_x * 600
    elif "right" in context_lower:
        penalty += (1 - norm_x) * 600
    elif "center" in context_lower:
        penalty += abs(norm_x - 0.5) * 400

    return penalty


def score_ocr_candidate(
    item: Any,
    target_lower: str,
    screenshot_width: int,
    screenshot_height: int,
    visual_context: Optional[str] = None,
) -> tuple[float, str]:
    """
    Score an OCR candidate for click targeting.

    Args:
        item: OCR result with text, center, and confidence attributes
        target_lower: Target text in lowercase
        screenshot_width: Width of screenshot
        screenshot_height: Height of screenshot
        visual_context: Spatial context for scoring

    Returns:
        Tuple of (score, relation_type)
    """
    raw_text = (item.text or "").strip()
    if not raw_text:
        return (-999.0, "none")

    text_lower = raw_text.lower()
    relation = determine_text_relation(text_lower, target_lower)

    if relation == "none":
        return (-999.0, "none")

    # Filter out bad substring matches
    length_delta = abs(len(text_lower) - len(target_lower))
    if relation == "substring":
        if length_delta > 2 or not is_word_boundary_match(text_lower, target_lower):
            return (-999.0, "none")

    # Base scores by relation type
    base_score = {
        "exact": 1000,
        "prefix": 750,
        "word": 650,
        "substring": 450,
        "partial": 350,
    }[relation]

    score = float(base_score) + float(item.confidence or 0.0) * 100.0

    # Length bonus for exact/word matches
    if relation in {"exact", "word"}:
        score += 500.0 / (len(text_lower) + 1)

    # Spatial penalty
    center_x, center_y = item.center
    position_penalty = compute_spatial_score(
        center_x, center_y, screenshot_width, screenshot_height, visual_context
    )

    score -= position_penalty

    return (score, relation)


def filter_candidates_by_spatial_context(
    candidates: List[Any],
    visual_context: str,
    screenshot_width: int,
    screenshot_height: int,
) -> List[Any]:
    """
    Filter OCR candidates by spatial context keywords.

    Args:
        candidates: List of OCR items with center coordinates
        visual_context: Spatial keywords (e.g., "top", "left sidebar", "first")
        screenshot_width: Width of screenshot
        screenshot_height: Height of screenshot

    Returns:
        Filtered list of candidates
    """
    if not visual_context or not candidates:
        return candidates

    context_lower = visual_context.lower()
    filtered = candidates.copy()

    # Vertical filtering
    if "top" in context_lower or "above" in context_lower:
        filtered = [
            item for item in filtered if item.center[1] < screenshot_height * 0.4
        ]
    elif "bottom" in context_lower or "below" in context_lower:
        filtered = [
            item for item in filtered if item.center[1] > screenshot_height * 0.6
        ]
    elif "middle" in context_lower or "center" in context_lower:
        filtered = [
            item
            for item in filtered
            if screenshot_height * 0.3 < item.center[1] < screenshot_height * 0.7
        ]

    # Horizontal filtering
    if "left" in context_lower:
        filtered = [
            item for item in filtered if item.center[0] < screenshot_width * 0.4
        ]
    elif "right" in context_lower:
        filtered = [
            item for item in filtered if item.center[0] > screenshot_width * 0.6
        ]

    # Order filtering
    if "first" in context_lower:
        filtered = sorted(filtered, key=lambda item: (item.center[1], item.center[0]))[
            :3
        ]
    elif "last" in context_lower:
        filtered = sorted(filtered, key=lambda item: (item.center[1], item.center[0]))[
            -3:
        ]

    return filtered if filtered else candidates
