"""
Linux-specific role normalization.

Converts Linux AT-SPI roles (push button, text, combo box, etc.) to
platform-agnostic format (Button, TextField, ComboBox, etc.) before
passing to the shared registry.

This is the ONLY place where AT-SPI-specific role handling should exist.
"""

from typing import Any, Dict, Optional


ATSPI_TO_COMMON = {
    "PushButton": "Button",
    "Text": "TextField",
    "PasswordText": "SecureTextField",
    "Entry": "TextField",
    "SpinButton": "Slider",
    "ToggleButton": "Button",
    "ScrollBar": "Slider",
    "StatusBar": "StatusText",
    "Accelerator": "MenuItem",
    "Filler": "Group",
    "Panel": "Group",
    "Viewport": "Group",
    "LayeredPane": "Group",
    "RootPane": "Group",
    "GlassPane": "Group",
    "OptionPane": "Group",
    "InternalFrame": "Window",
    "DesktopIcon": "Icon",
    "DesktopFrame": "Window",
    "Alert": "Dialog",
    "ColorChooser": "ColorWell",
    "DirectoryPane": "FileChooser",
    "FileChooser": "FileChooser",
    "PasswordField": "SecureTextField",
    "PopupMenu": "Menu",
    "TearOffMenuItem": "MenuItem",
    "Terminal": "TextArea",
    "EditBar": "TextField",
    "DocumentFrame": "TextArea",
    "DocumentText": "TextArea",
    "DocumentSpreadsheet": "Table",
    "DocumentPresentation": "Document",
    "DocumentEmail": "Document",
    "Autocomplete": "ComboBox",
    "Caption": "StaticText",
    "Heading": "StaticText",
    "Paragraph": "StaticText",
    "BlockQuote": "StaticText",
    "Section": "Group",
    "Form": "Group",
    "Redundant": "Unknown",
    "Embedded": "Group",
}


def normalize_linux_role(atspi_role: str) -> str:
    """
    Normalize Linux AT-SPI role to platform-agnostic format.

    AT-SPI uses lowercase with spaces: "push button", "text", "combo box"
    We normalize to PascalCase and map common names.

    Handles unknown roles gracefully - converts to PascalCase and passes through.

    Args:
        atspi_role: AT-SPI role name (e.g., "push button", "text", "combo box")

    Returns:
        Normalized role (e.g., "Button", "TextField", "ComboBox")
    """
    if not atspi_role:
        return ""

    pascal_case = atspi_role.title().replace(" ", "").replace("-", "")

    return ATSPI_TO_COMMON.get(pascal_case, pascal_case)


def normalize_linux_element(
    node: Any,
    pyatspi_module: Any,
    app_name: str,
    screen_width: int,
    screen_height: int,
    parent_path: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Extract and normalize element data from pyatspi node.

    Uses actual pyatspi API:
    - node.getRoleName() returns lowercase string
    - node.queryComponent().getExtents(DESKTOP_COORDS)
    - node.queryAction().nActions for has_actions
    - node.getState().contains(STATE_ENABLED/FOCUSED)

    Args:
        node: pyatspi accessible node
        pyatspi_module: The pyatspi module (for constants)
        app_name: Application name
        screen_width: Screen width for bounds validation
        screen_height: Screen height for bounds validation
        parent_path: Hash of ancestor context (optional)

    Returns:
        Normalized element dictionary matching shared registry schema,
        or None if element should be skipped (invalid bounds, etc.)
    """
    try:
        role = node.getRoleName() if hasattr(node, "getRoleName") else ""

        x, y, w, h = 0, 0, 0, 0
        try:
            component = node.queryComponent()
            extents = component.getExtents(pyatspi_module.DESKTOP_COORDS)
            x, y, w, h = extents.x, extents.y, extents.width, extents.height
        except Exception:
            pass

        if w <= 0 or h <= 0:
            return None

        if x < 0 or y < 0 or x > screen_width or y > screen_height:
            return None

        name = getattr(node, "name", "") or ""
        description = getattr(node, "description", "") or ""
        label = name or description

        has_actions = False
        try:
            action_iface = node.queryAction()
            has_actions = action_iface.nActions > 0
        except Exception:
            pass

        is_enabled = False
        is_focused = False
        try:
            state = node.getState()
            is_enabled = state.contains(pyatspi_module.STATE_ENABLED)
            is_focused = state.contains(pyatspi_module.STATE_FOCUSED)
        except Exception:
            pass

        identifier = ""
        try:
            idx = node.getIndexInParent()
            if idx is not None:
                identifier = str(idx)
        except Exception:
            pass

        if not label:
            label = role or ""

        role_desc = ""
        try:
            role_desc = (
                node.getLocalizedRoleName()
                if hasattr(node, "getLocalizedRoleName")
                else ""
            )
        except Exception:
            pass

        return {
            "role": normalize_linux_role(role),
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
            role = ancestor.getRoleName() if hasattr(ancestor, "getRoleName") else ""
            if role:
                roles.append(normalize_linux_role(role))
        except Exception:
            continue

    if not roles:
        return ""

    path_str = "|".join(roles)
    return hashlib.md5(path_str.encode()).hexdigest()[:6]
