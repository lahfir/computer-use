"""
One test: Open Calculator, get elements, click every button.
Uses native references directly - no stale element issues.
"""

import pytest
import sys
import time
import subprocess


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_click_all_calculator_buttons():
    subprocess.run(["open", "-a", "Calculator"], check=True)
    time.sleep(1.5)

    from computer_use.tools.accessibility import get_accessibility_tool

    acc = get_accessibility_tool()
    assert acc.available, "Accessibility not available"

    elements = acc.get_elements("Calculator", interactive_only=True)
    print(f"\nGot {len(elements)} elements")
    assert len(elements) > 0, "No elements found"

    buttons = [e for e in elements if "button" in (e.get("role") or "").lower()]
    print(f"Found {len(buttons)} buttons")
    assert len(buttons) > 0, "No buttons found"

    clicked = 0
    failed = 0
    for btn in buttons:
        node = btn.get("_native_ref") or btn.get("_element")
        if not node:
            continue

        try:
            if hasattr(node, "Press"):
                node.Press()
                clicked += 1
            elif hasattr(node, "AXPress"):
                node.AXPress()
                clicked += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {e}")

        time.sleep(0.05)

    print(f"\nClicked {clicked}/{len(buttons)} buttons, {failed} failed")
    assert clicked > 0, "No clicks succeeded"
    assert clicked > len(buttons) * 0.5, f"Less than 50% succeeded: {clicked}/{len(buttons)}"

    subprocess.run(["osascript", "-e", 'quit app "Calculator"'], capture_output=True)
