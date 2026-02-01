"""
Pytest configuration and fixtures for REAL GUI tool testing.

This module provides real tool registry setup for testing against actual applications.
NO MOCKING - all tests interact with REAL apps and REAL UI elements.
"""

import sys
import time
import subprocess
from pathlib import Path
from typing import Generator, List, Optional

import pytest


def pytest_configure(config):
    """Configure pytest."""
    src_path = Path(__file__).parent.parent / "src"
    sys.path.insert(0, str(src_path))

    config.addinivalue_line("markers", "real: mark test as using real apps")
    config.addinivalue_line("markers", "workflow: mark test as workflow test")
    config.addinivalue_line("markers", "calculator: mark test as using Calculator app")
    config.addinivalue_line("markers", "finder: mark test as using Finder app")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "destructive: mark test as destructive")

    print("\n" + "=" * 80)
    print("PYTEST CONFIGURATION - REAL GUI TESTS")
    print("=" * 80)
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   Platform: {sys.platform}")
    print(f"   Src path: {src_path}")
    print("=" * 80 + "\n")


def pytest_collection_modifyitems(config, items):
    """Modify test items to add helpful markers."""
    for item in items:
        if "accessibility" in item.nodeid.lower():
            item.add_marker("accessibility")
        if "ocr" in item.nodeid.lower():
            item.add_marker("ocr")
        if "screenshot" in item.nodeid.lower():
            item.add_marker("screenshot")
        if "integration" in item.nodeid.lower():
            item.add_marker("integration")
        if "_real" in item.nodeid.lower():
            item.add_marker("real")
        if "calculator" in item.nodeid.lower():
            item.add_marker("calculator")
        if "finder" in item.nodeid.lower():
            item.add_marker("finder")
        if "workflow" in item.nodeid.lower():
            item.add_marker("workflow")


@pytest.fixture(scope="module")
def real_tool_registry():
    """
    Create REAL tool registry with all tools initialized.

    This fixture creates actual platform tools:
    - ScreenshotTool: Captures real screenshots
    - OCRTool: Performs real OCR on images
    - InputTool: Sends real mouse/keyboard input
    - ProcessTool: Launches real applications
    - AccessibilityTool: Uses real accessibility APIs

    Returns:
        PlatformToolRegistry with all tools initialized
    """
    from computer_use.utils.platform import detect_platform
    from computer_use.tools.platform_registry import PlatformToolRegistry
    from computer_use.utils.validation import CoordinateValidator, SafetyChecker

    capabilities = detect_platform()
    safety_checker = SafetyChecker()
    coord_validator = CoordinateValidator(
        screen_width=capabilities.screen_resolution[0],
        screen_height=capabilities.screen_resolution[1],
    )

    registry = PlatformToolRegistry(
        capabilities=capabilities,
        safety_checker=safety_checker,
        coordinate_validator=coord_validator,
    )

    return registry


@pytest.fixture
def cleanup_apps() -> Generator[List[str], None, None]:
    """
    Fixture to track and cleanup test apps after each test.

    Usage:
        def test_something(cleanup_apps):
            cleanup_apps.append("Calculator")
            # ... test code ...
        # Calculator will be closed after test

    Yields:
        List to append app names for cleanup
    """
    opened_apps: List[str] = []
    yield opened_apps

    for app in opened_apps:
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e", f'quit app "{app}"'],
                    capture_output=True,
                    timeout=5,
                )
            elif sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/IM", f"{app}.exe", "/F"],
                    capture_output=True,
                    timeout=5,
                )
            else:
                subprocess.run(
                    ["pkill", "-f", app],
                    capture_output=True,
                    timeout=5,
                )
            time.sleep(0.5)
        except Exception:
            pass


@pytest.fixture
def wait_for_app():
    """
    Fixture providing a helper function to wait for an app to be ready.

    Returns:
        Function that waits for app readiness
    """
    def _wait(app_name: str, timeout: float = 5.0) -> bool:
        """Wait for app to appear in accessibility API."""
        start = time.time()
        while (time.time() - start) < timeout:
            try:
                if sys.platform == "darwin":
                    result = subprocess.run(
                        ["osascript", "-e", f'tell app "{app_name}" to count windows'],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        count = int(result.stdout.strip())
                        if count > 0:
                            return True
            except Exception:
                pass
            time.sleep(0.3)
        return False
    return _wait


@pytest.fixture
def focus_app():
    """
    Fixture providing a helper function to focus an app.

    Returns:
        Function that focuses an app
    """
    def _focus(app_name: str) -> bool:
        """Focus an app by name."""
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e", f'tell app "{app_name}" to activate'],
                    capture_output=True,
                    timeout=2,
                )
                time.sleep(0.3)
                return True
        except Exception:
            pass
        return False
    return _focus


@pytest.fixture
def close_app():
    """
    Fixture providing a helper function to close an app.

    Returns:
        Function that closes an app
    """
    def _close(app_name: str) -> bool:
        """Close an app by name."""
        try:
            if sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e", f'quit app "{app_name}"'],
                    capture_output=True,
                    timeout=5,
                )
                time.sleep(0.5)
                return True
            elif sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/IM", f"{app_name}.exe", "/F"],
                    capture_output=True,
                    timeout=5,
                )
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False
    return _close


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests",
    )
    parser.addoption(
        "--run-destructive",
        action="store_true",
        default=False,
        help="Run tests that modify system state",
    )


def pytest_runtest_setup(item):
    """Skip slow/destructive tests unless explicitly enabled."""
    if "slow" in item.keywords and not item.config.getoption("--run-slow"):
        pytest.skip("Skipping slow test (use --run-slow to run)")
    if "destructive" in item.keywords and not item.config.getoption("--run-destructive"):
        pytest.skip("Skipping destructive test (use --run-destructive to run)")
