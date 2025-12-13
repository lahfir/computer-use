"""
Centralized logging configuration for suppressing verbose third-party logs.
"""

import logging
import os
import warnings


NOISY_LIBRARIES = [
    "easyocr",
    "paddleocr",
    "werkzeug",
    "flask",
    "urllib3",
    "httpx",
    "httpcore",
    "google",
    "google.genai",
    "google.auth",
    "google.api_core",
    "google.generativeai",
    "langchain_google_genai",
    "litellm",
    "crewai",
    "grpc",
]

BROWSER_LOGGERS = [
    "browser_use",
    "browser_use.agent",
    "browser_use.browser",
    "browser_use.tools",
    "browser_use.service",
    "browser_use.controller",
    "BrowserSession",
    "Agent",
]


class NullHandler(logging.Handler):
    """Handler that discards all log records."""

    def emit(self, record):
        pass


class GoogleApiKeyFilter(logging.Filter):
    """Filter to suppress Google API key duplicate warnings."""

    def filter(self, record):
        message = record.getMessage()
        if "Both GOOGLE_API_KEY and GEMINI_API_KEY" in message:
            return False
        if "Using GOOGLE_API_KEY" in message:
            return False
        return True


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging levels to suppress verbose output from third-party libraries.
    Sets up environment variables and configures all noisy loggers.

    Args:
        verbose: If True, allow browser-use logs to print. If False, silence them.
    """
    warnings.filterwarnings("ignore")
    # Suppress Google API key duplicate warnings specifically
    warnings.filterwarnings(
        "ignore",
        message=".*Both GOOGLE_API_KEY and GEMINI_API_KEY.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=".*Using GOOGLE_API_KEY.*",
        category=UserWarning,
    )

    os.environ["GRPC_VERBOSITY"] = "ERROR"
    os.environ["GLOG_minloglevel"] = "2"
    os.environ["PPOCR_SHOW_LOG"] = "False"
    os.environ["BROWSER_USE_LOGGING_LEVEL"] = "CRITICAL" if not verbose else "INFO"

    api_key_filter = GoogleApiKeyFilter()

    for logger_name in NOISY_LIBRARIES:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
        logger.handlers = [NullHandler()]
        logger.addFilter(api_key_filter)

    root_logger = logging.getLogger()
    root_logger.addFilter(api_key_filter)

    browser_level = logging.INFO if verbose else logging.CRITICAL

    for logger_name in BROWSER_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(browser_level)
        logger.propagate = False
        logger.handlers = [NullHandler()] if not verbose else []

    werkzeug = logging.getLogger("werkzeug")
    werkzeug.disabled = True


def silence_flask_logs() -> None:
    """
    Silence Flask and Werkzeug logs for background servers.
    Call this before starting Flask apps.
    """
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.CRITICAL)
    log.disabled = True

    flask_log = logging.getLogger("flask")
    flask_log.setLevel(logging.CRITICAL)
    flask_log.disabled = True


def silence_browser_logs() -> None:
    """
    Completely silence browser-use library logs.
    Call this after browser-use is imported to override its handlers.
    """
    for logger_name in BROWSER_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
        logger.handlers = [NullHandler()]
