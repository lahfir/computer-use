"""
macOS-specific role normalization.

Converts macOS accessibility roles (AXButton, AXTextField, etc.)
to platform-agnostic format (Button, TextField, etc.) before
passing to the shared registry.

This is the ONLY place where "AX" prefix handling should exist.
"""

from typing import Any, Dict, Optional


def normalize_macos_role(ax_role: str) -> str:
    """
    Normalize macOS accessibility role to platform-agnostic format.

    macOS uses "AX" prefix: AXButton, AXTextField, AXStaticText
    We strip it: Button, TextField, StaticText

    Handles unknown roles gracefully - just strips AX prefix if present.

    Args:
        ax_role: macOS accessibility role (e.g., "AXButton", "AXTextField")

    Returns:
        Normalized role (e.g., "Button", "TextField")
    """
    if not ax_role:
        return ""

    if ax_role.startswith("AX"):
        return ax_role[2:]

    return ax_role


def get_best_label(node: Any) -> str:
    """
    Get the best available label for a macOS accessibility element.

    Tries multiple attributes in order of preference:
    1. AXTitle - explicit title
    2. AXDescription - accessibility description
    3. AXValue - current value (useful for text fields)
    4. AXPlaceholderValue - placeholder text

    Args:
        node: atomacos accessibility node

    Returns:
        Best available label string, or empty string if none found
    """
    try:
        title = getattr(node, "AXTitle", None)
        if title:
            return str(title)

        description = getattr(node, "AXDescription", None)
        if description:
            return str(description)

        value = getattr(node, "AXValue", None)
        if value:
            value_str = str(value)
            if len(value_str) <= 100:
                return value_str

        placeholder = getattr(node, "AXPlaceholderValue", None)
        if placeholder:
            return str(placeholder)

    except Exception:
        pass

    return ""


def normalize_macos_element(
    node: Any,
    app_name: str,
    parent_path: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Extract and normalize element data from atomacos node.

    Uses actual atomacos API:
    - AXRole, AXTitle, AXDescription, AXIdentifier
    - AXPosition (tuple), AXSize (tuple)
    - AXEnabled, AXFocused, AXActions

    Args:
        node: atomacos accessibility node
        app_name: Application name
        parent_path: Hash of ancestor context (optional)

    Returns:
        Normalized element dictionary matching shared registry schema,
        or None if element should be skipped (invalid bounds, etc.)
    """
    try:
        role = str(getattr(node, "AXRole", ""))

        if not hasattr(node, "AXPosition") or not hasattr(node, "AXSize"):
            return None

        pos = node.AXPosition
        size = node.AXSize

        if pos is None or size is None:
            return None

        x, y = pos[0], pos[1]
        w, h = size[0], size[1]

        if w <= 0 or h <= 0:
            return None

        if x < -100 or y < -100:
            return None

        label = get_best_label(node)

        identifier = str(getattr(node, "AXIdentifier", "") or "")

        actions = getattr(node, "AXActions", []) or []
        has_actions = len(actions) > 0

        is_enabled = bool(getattr(node, "AXEnabled", True))
        is_focused = bool(getattr(node, "AXFocused", False))

        role_desc = ""
        try:
            role_desc = str(getattr(node, "AXRoleDescription", "") or "")
        except Exception:
            pass

        return {
            "role": normalize_macos_role(role),
            "label": label,
            "identifier": identifier,
            "app_name": app_name,
            "center": [int(x + w / 2), int(y + h / 2)],
            "bounds": [int(x), int(y), int(w), int(h)],
            "has_actions": has_actions,
            "enabled": is_enabled,
            "focused": is_focused,
            "role_description": role_desc,
            "parent_path": parent_path,
            "_native_ref": node,
        }

    except Exception:
        return None


def compute_parent_path(ancestors: list) -> str:
    """
    Compute a hash path from ancestor roles for element uniqueness.

    Args:
        ancestors: List of ancestor nodes (bottom to top)

    Returns:
        Short hash representing the ancestor path
    """
    import hashlib

    roles = []
    for ancestor in ancestors[:5]:
        try:
            role = str(getattr(ancestor, "AXRole", ""))
            if role:
                roles.append(normalize_macos_role(role))
        except Exception:
            continue

    if not roles:
        return ""

    path_str = "|".join(roles)
    return hashlib.md5(path_str.encode()).hexdigest()[:6]
