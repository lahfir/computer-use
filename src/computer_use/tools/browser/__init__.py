"""
Browser-Use tools loader.
Loads and initializes all browser tools automatically.
"""

from typing import Optional, Tuple


def load_browser_tools(gui_delegate=None) -> Tuple[Optional[object], bool, bool]:
    """
    Load all Browser-Use tools dynamically.

    Args:
        gui_delegate: Optional callable to delegate GUI tasks to GUI agent.

    Returns:
        Tuple of (Tools object, has_twilio, has_image_gen)
    """
    from .twilio_tools import load_twilio_tools
    from .image_tools import load_image_tools
    from .delegation_tools import load_delegation_tools
    from .paste_tools import load_paste_tools

    twilio_tools = load_twilio_tools()
    image_tools = load_image_tools()
    delegation_tools = load_delegation_tools(gui_delegate)
    paste_tools = load_paste_tools()

    has_twilio = twilio_tools is not None
    has_image_gen = image_tools is not None

    base_tools = None

    for toolset in [paste_tools, delegation_tools, twilio_tools, image_tools]:
        if toolset:
            if base_tools:
                base_tools.registry.registry.actions.update(
                    toolset.registry.registry.actions
                )
            else:
                base_tools = toolset

    return base_tools, has_twilio, has_image_gen
