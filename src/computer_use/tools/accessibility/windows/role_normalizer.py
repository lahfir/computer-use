"""
Windows-specific role normalization.

Converts Windows UIA control types (Edit, Button, etc.) to platform-agnostic
format (TextField, Button, etc.) before passing to the shared registry.

This is the ONLY place where Windows-specific role mapping should exist.
"""

from typing import Any, Dict, Optional


WINDOWS_TO_COMMON = {
    "Edit": "TextField",
    "Document": "TextArea",
    "DataItem": "ListItem",
    "DataGrid": "Table",
    "Tree": "Outline",
    "TreeItem": "OutlineRow",
    "Header": "HeaderRow",
    "HeaderItem": "HeaderCell",
}


def normalize_windows_role(control_type: str) -> str:
    """
    Normalize Windows UIA control type to platform-agnostic format.

    Windows uses: Button, Edit, ComboBox, CheckBox, etc.
    Map Windows-specific names to common names for consistency.

    Handles unknown roles gracefully - passes them through as-is.

    Args:
        control_type: Windows UIA control type (e.g., "Edit", "Button")

    Returns:
        Normalized role (e.g., "TextField", "Button")
    """
    if not control_type:
        return ""

    return WINDOWS_TO_COMMON.get(control_type, control_type)


def normalize_windows_element(
    node: Any,
    app_name: str,
    screen_width: int,
    screen_height: int,
    parent_path: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Extract and normalize element data from pywinauto node.

    Uses actual pywinauto API:
    - node.element_info.control_type
    - node.element_info.name
    - node.rectangle() returns object with .left, .top, .width(), .height()
    - node.is_enabled(), node.has_focus()

    Args:
        node: pywinauto element wrapper
        app_name: Application name
        screen_width: Screen width for bounds validation
        screen_height: Screen height for bounds validation
        parent_path: Hash of ancestor context (optional)

    Returns:
        Normalized element dictionary matching shared registry schema,
        or None if element should be skipped (invalid bounds, etc.)
    """
    try:
        rect = node.rectangle()
        x, y = rect.left, rect.top
        w, h = rect.width(), rect.height()

        if w <= 0 or h <= 0:
            return None

        if x < 0 or y < 0 or x > screen_width or y > screen_height:
            return None

        control_type = ""
        try:
            control_type = node.element_info.control_type or ""
        except Exception:
            pass

        name = ""
        try:
            name = getattr(node.element_info, "name", "") or ""
        except Exception:
            pass

        window_text = ""
        try:
            window_text = node.window_text() or ""
        except Exception:
            pass

        label = name or window_text

        identifier = ""
        try:
            runtime_id = getattr(node.element_info, "runtime_id", None)
            if runtime_id:
                identifier = str(runtime_id)
        except Exception:
            pass

        automation_id = ""
        try:
            automation_id = getattr(node.element_info, "automation_id", "") or ""
        except Exception:
            automation_id = ""

        if not identifier and automation_id:
            identifier = automation_id

        if not label and automation_id:
            label = automation_id

        is_enabled = False
        try:
            is_enabled = node.is_enabled()
        except Exception:
            pass

        is_focused = False
        try:
            is_focused = node.has_focus()
        except Exception:
            pass

        role_desc = ""
        try:
            role_desc = str(
                getattr(node.element_info, "localized_control_type", "") or ""
            )
        except Exception:
            pass

        return {
            "role": normalize_windows_role(control_type),
            "label": label,
            "identifier": identifier,
            "app_name": app_name,
            "center": [int(x + w / 2), int(y + h / 2)],
            "bounds": [int(x), int(y), int(w), int(h)],
            "has_actions": True,
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
    Compute a hash path from ancestor control types for element uniqueness.

    Args:
        ancestors: List of ancestor nodes (bottom to top)

    Returns:
        Short hash representing the ancestor path
    """
    import hashlib

    roles = []
    for ancestor in ancestors[:5]:
        try:
            control_type = ancestor.element_info.control_type or ""
            if control_type:
                roles.append(normalize_windows_role(control_type))
        except Exception:
            continue

    if not roles:
        return ""

    path_str = "|".join(roles)
    return hashlib.md5(path_str.encode()).hexdigest()[:6]
