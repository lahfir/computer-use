"""
Tests for refactored accessibility - fast, no stale errors.

These tests verify that the SimpleElementStore-based accessibility
works correctly without epoch-based staleness errors.
"""

import pytest
import sys
import time
import subprocess


@pytest.fixture
def calculator_app():
    """Open Calculator app for testing, close when done."""
    subprocess.run(["osascript", "-e", 'quit app "Calculator"'], capture_output=True)
    time.sleep(0.5)

    for attempt in range(3):
        result = subprocess.run(["open", "-a", "Calculator"], capture_output=True)
        if result.returncode == 0:
            break
        time.sleep(1.0)
    else:
        pytest.skip("Could not open Calculator app")

    time.sleep(1.5)
    yield "Calculator"
    subprocess.run(["osascript", "-e", 'quit app "Calculator"'], capture_output=True)
    time.sleep(0.3)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
class TestAccessibilityRefactored:
    """Tests for the refactored accessibility system."""

    def test_click_all_buttons_no_stale_errors(self, calculator_app):
        """Click all buttons without any STALE errors."""
        from computer_use.tools.accessibility import get_accessibility_tool

        acc = get_accessibility_tool()
        assert acc.available, "Accessibility not available"

        elements = acc.get_elements(calculator_app, interactive_only=True)
        print(f"\nGot {len(elements)} elements")
        assert len(elements) > 0, "No elements found"

        buttons = [e for e in elements if "button" in (e.get("role") or "").lower()]
        print(f"Found {len(buttons)} buttons")
        assert len(buttons) > 0, "No buttons found"

        clicked = 0
        failed = 0
        stale_errors = 0

        for btn in buttons:
            element_id = btn.get("element_id")
            if not element_id:
                continue

            success, msg = acc.click_by_id(element_id)
            if success:
                clicked += 1
            else:
                failed += 1
                if "STALE" in msg.upper():
                    stale_errors += 1
                    print(f"  STALE ERROR: {msg}")
            time.sleep(0.05)

        print(f"\nClicked {clicked}/{len(buttons)}, failed {failed}, stale errors {stale_errors}")
        assert stale_errors == 0, f"Got {stale_errors} STALE errors - this should be 0!"
        assert clicked > len(buttons) * 0.8, f"Expected >80% success: {clicked}/{len(buttons)}"

    def test_multiple_sequential_clicks_same_element(self, calculator_app):
        """Click same element multiple times without re-fetching."""
        from computer_use.tools.accessibility import get_accessibility_tool

        acc = get_accessibility_tool()
        elements = acc.get_elements(calculator_app, interactive_only=True)
        buttons = [e for e in elements if "button" in (e.get("role") or "").lower()]

        btn = next(
            (e for e in buttons if e.get("label") == "5"),
            next((e for e in buttons if e.get("label") == "C"), None)
        )
        if not btn:
            btn = buttons[0] if buttons else None
        assert btn, "Should find a button to click"

        element_id = btn.get("element_id")
        assert element_id, "Button should have element_id"
        label = btn.get("label", "button")

        for i in range(10):
            success, msg = acc.click_by_id(element_id)
            assert success, f"Click {i+1} failed: {msg}"
            time.sleep(0.05)

        print(f"\nSuccessfully clicked button '{label}' 10 times without re-fetching")

    def test_click_speed_benchmark(self, calculator_app):
        """Verify clicking is fast (>5 clicks/second)."""
        from computer_use.tools.accessibility import get_accessibility_tool

        acc = get_accessibility_tool()
        elements = acc.get_elements(calculator_app, interactive_only=True)
        buttons = [e for e in elements if "button" in (e.get("role") or "").lower()][:20]

        assert len(buttons) >= 10, f"Need at least 10 buttons, got {len(buttons)}"

        start = time.time()
        successful = 0
        for btn in buttons:
            element_id = btn.get("element_id")
            if element_id:
                success, _ = acc.click_by_id(element_id)
                if success:
                    successful += 1
        elapsed = time.time() - start

        clicks_per_second = successful / elapsed if elapsed > 0 else 0
        print(f"\n{successful} clicks in {elapsed:.2f}s = {clicks_per_second:.1f} clicks/sec")

        assert clicks_per_second > 5, f"Too slow: {clicks_per_second:.1f} clicks/sec (need >5)"

    def test_direct_native_ref_clicking(self, calculator_app):
        """Test direct native ref clicking (like the working test)."""
        from computer_use.tools.accessibility import get_accessibility_tool

        acc = get_accessibility_tool()
        elements = acc.get_elements(calculator_app, interactive_only=True)
        buttons = [e for e in elements if "button" in (e.get("role") or "").lower()]

        clicked = 0
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
            except Exception:
                pass

        print(f"\nDirect native clicks: {clicked}/{len(buttons)}")
        assert clicked > len(buttons) * 0.8, f"Expected >80% success: {clicked}/{len(buttons)}"

    def test_calculator_workflow_2_plus_2(self, calculator_app):
        """Full workflow: 2 + 2 = 4."""
        from computer_use.tools.accessibility import get_accessibility_tool

        acc = get_accessibility_tool()
        elements = acc.get_elements(calculator_app, interactive_only=True)
        buttons = [e for e in elements if "button" in (e.get("role") or "").lower()]

        def find_btn(label):
            for e in buttons:
                if e.get("label") == label:
                    return e
            return None

        for label in ["2", "+", "2", "="]:
            btn = find_btn(label)
            if not btn:
                pytest.skip(f"Button '{label}' not found - Calculator UI may differ")

            element_id = btn.get("element_id")
            assert element_id, f"Button '{label}' should have element_id"

            success, msg = acc.click_by_id(element_id)
            assert success, f"Failed to click '{label}': {msg}"
            time.sleep(0.1)

        print("\nSuccessfully calculated 2 + 2")

    def test_interleaved_fetch_and_click(self, calculator_app):
        """Verify that fetching doesn't break existing element IDs."""
        from computer_use.tools.accessibility import get_accessibility_tool

        acc = get_accessibility_tool()

        elements1 = acc.get_elements(calculator_app, interactive_only=True)
        buttons = [e for e in elements1 if "button" in (e.get("role") or "").lower()]

        if len(buttons) < 2:
            pytest.skip("Not enough buttons found")

        btn_1 = buttons[0]
        id_1 = btn_1.get("element_id")
        assert id_1, "First button should have element_id"

        success1, _ = acc.click_by_id(id_1)
        assert success1, "First click should succeed"

        elements2 = acc.get_elements(calculator_app, interactive_only=True, use_cache=False)
        buttons2 = [e for e in elements2 if "button" in (e.get("role") or "").lower()]
        btn_2 = buttons2[1] if len(buttons2) > 1 else buttons2[0]
        id_2 = btn_2.get("element_id")

        success2, _ = acc.click_by_id(id_2)
        assert success2, "Second click should succeed after re-fetch"

        success1_again, msg = acc.click_by_id(id_1)
        assert success1_again, f"Original ID should still work: {msg}"

        print("\nInterleaved fetch and click works correctly")

    def test_element_store_basic_operations(self):
        """Test SimpleElementStore basic operations."""
        from computer_use.tools.accessibility.element_store import SimpleElementStore

        store = SimpleElementStore()

        element1 = {
            "role": "Button",
            "label": "Save",
            "identifier": "save-btn",
            "center": [100, 100],
            "bounds": [50, 50, 100, 50],
            "_native_ref": object(),
        }

        eid1 = store.store(element1, "TestApp")
        assert eid1.startswith("e_but_save_")

        retrieved = store.get(eid1)
        assert retrieved is not None
        assert retrieved["label"] == "Save"

        assert store.get("nonexistent") is None

        element2 = {
            "role": "Button",
            "label": "Cancel",
            "identifier": "cancel-btn",
            "center": [200, 100],
            "bounds": [150, 50, 100, 50],
            "_native_ref": object(),
        }
        store.store(element2, "TestApp")

        assert store.count == 2

        cleared = store.clear_app("TestApp")
        assert cleared == 2
        assert store.count == 0

        print("\nSimpleElementStore basic operations work correctly")
