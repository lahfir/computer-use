"""
Main entry point for computer use automation agent.
"""

import asyncio
import sys

from .crew import ComputerUseCrew
from .utils.command_confirmation import CommandConfirmation
from .utils.logging_config import setup_logging
from .utils.permissions import check_and_request_permissions
from .utils.platform_detector import detect_platform
from .utils.safety_checker import SafetyChecker
from .utils.ui import (
    VerbosityLevel,
    console,
    dashboard,
    get_task_input,
    print_banner,
    print_platform_info,
    print_section_header,
    print_status_overview,
    print_task_result,
    THEME,
)


async def main(
    voice_input: bool = False,
    use_browser_profile: bool = False,
    browser_profile: str = "Default",
    verbosity: VerbosityLevel = VerbosityLevel.NORMAL,
):
    """
    Main execution function.

    Args:
        voice_input: Start with voice input mode enabled
        use_browser_profile: Use existing Chrome profile for authentication
        browser_profile: Chrome profile name (Default, Profile 1, etc.)
        verbosity: Output verbosity level (QUIET, NORMAL, VERBOSE)
    """
    import logging
    import os
    import warnings

    dashboard.set_verbosity(verbosity)

    warnings.filterwarnings("ignore")
    os.environ["PPOCR_SHOW_LOG"] = "False"

    for logger_name in [
        "easyocr",
        "paddleocr",
        "werkzeug",
        "flask",
    ]:
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)
        logging.getLogger(logger_name).propagate = False

    setup_logging()

    print_banner()

    if not check_and_request_permissions():
        console.print(f"[{THEME['warning']}]Exiting due to missing permissions.[/]")
        sys.exit(1)

    print_section_header("Platform Detection", "")
    capabilities = detect_platform()
    print_platform_info(capabilities)

    print_section_header("Initializing", "")

    from .config.llm_config import LLMConfig
    from .services.twilio_service import TwilioService
    from .services.webhook_server import WebhookServer
    from .utils.ui import print_twilio_config_status

    twilio_service = TwilioService()
    twilio_service.set_llm_client(LLMConfig.get_llm())

    webhook_server = None
    if twilio_service.is_configured():
        print_twilio_config_status(True, twilio_service.get_phone_number())
        webhook_server = WebhookServer(twilio_service)
        webhook_server.start()
    else:
        print_twilio_config_status(False)

    crew = ComputerUseCrew(
        capabilities,
        SafetyChecker(),
        confirmation_manager=CommandConfirmation(),
        use_browser_profile=use_browser_profile,
        browser_profile_directory=browser_profile,
    )

    system_status = {
        "Tools": f"{len(crew.tool_registry.list_available_tools())} loaded",
        "Webhook": f"Port {webhook_server.port}" if webhook_server else "Off",
        "Browser": browser_profile if use_browser_profile else "Default",
    }
    print_status_overview("System", system_status)

    if verbosity == VerbosityLevel.NORMAL:
        console.print()
        console.print(f"  [{THEME['success']}]Ready[/]")
        console.print()

    conversation_history = []
    esc_pressed = {"value": False}

    def on_key_press(key):
        """Monitor for ESC key press."""
        try:
            from pynput import keyboard

            if key == keyboard.Key.esc:
                esc_pressed["value"] = True
        except Exception:
            pass

    from pynput import keyboard

    listener = keyboard.Listener(on_press=on_key_press)
    listener.start()

    try:
        while True:
            try:
                task = await get_task_input(start_with_voice=voice_input)

                if not task:
                    continue

                if task.lower() in ["quit", "exit", "q"]:
                    console.print(f"\n[bold {THEME['primary']}]Goodbye[/]")
                    break

                dashboard.set_task(task)

                if verbosity != VerbosityLevel.QUIET:
                    dashboard.start_dashboard()

                esc_pressed["value"] = False
                ComputerUseCrew.clear_cancellation()

                task_future = asyncio.create_task(
                    crew.execute_task(task, conversation_history)
                )

                while not task_future.done():
                    if esc_pressed["value"]:
                        dashboard.add_log_entry(
                            (
                                dashboard._action_log[-1].action_type
                                if dashboard._action_log
                                else __import__(
                                    "computer_use.utils.ui", fromlist=["ActionType"]
                                ).ActionType.ERROR
                            ),
                            "Cancelling task...",
                            status="error",
                        )
                        ComputerUseCrew.request_cancellation()
                        task_future.cancel()
                        try:
                            await task_future
                        except asyncio.CancelledError:
                            pass
                        break
                    await asyncio.sleep(0.1)

                dashboard.stop_dashboard()

                if not task_future.cancelled():
                    result = await task_future
                    conversation_history.append({"user": task, "result": result})

                    if len(conversation_history) > 10:
                        conversation_history = conversation_history[-10:]

                    print_task_result(result)
                else:
                    console.print(f"\n[{THEME['warning']}]Task cancelled[/]\n")

            except KeyboardInterrupt:
                dashboard.stop_dashboard()
                console.print(f"\n\n[{THEME['warning']}]Interrupted[/]")
                break
            except asyncio.CancelledError:
                dashboard.stop_dashboard()
                console.print(f"[{THEME['warning']}]Task cancelled[/]\n")
                continue
            except Exception as e:
                dashboard.stop_dashboard()
                console.print(f"\n[{THEME['error']}]Error: {e}[/]")
                if verbosity == VerbosityLevel.VERBOSE:
                    import traceback

                    traceback.print_exc()
    finally:
        listener.stop()
        dashboard.stop_dashboard()


def cli():
    """CLI entry point with argument parsing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Computer Use Agent - Multi-platform automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output with detailed logs",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Minimal output, no dashboard",
    )
    parser.add_argument(
        "--voice-input",
        action="store_true",
        help="Start with voice input mode enabled (toggle with F5)",
    )
    parser.add_argument(
        "--use-browser-profile",
        action="store_true",
        help="Use existing Chrome user profile for authenticated sessions",
    )
    parser.add_argument(
        "--browser-profile",
        type=str,
        default="Default",
        help="Chrome profile directory name (Default, Profile 1, etc.)",
    )

    args = parser.parse_args()

    if args.verbose and args.quiet:
        parser.error("Cannot use both --verbose and --quiet")

    if args.verbose:
        verbosity = VerbosityLevel.VERBOSE
    elif args.quiet:
        verbosity = VerbosityLevel.QUIET
    else:
        verbosity = VerbosityLevel.NORMAL

    try:
        asyncio.run(
            main(
                voice_input=args.voice_input,
                use_browser_profile=args.use_browser_profile,
                browser_profile=args.browser_profile,
                verbosity=verbosity,
            )
        )
    except KeyboardInterrupt:
        console.print(f"\n\n[bold {THEME['primary']}]Goodbye[/]")


if __name__ == "__main__":
    cli()
