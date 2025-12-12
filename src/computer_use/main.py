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
    ActionType,
    VerbosityLevel,
    console,
    dashboard,
    get_task_input,
    print_banner,
    print_platform_info,
    print_ready,
    print_startup_step,
    print_status_overview,
    print_task_result,
    startup_spinner,
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
    dashboard.set_verbosity(verbosity)
    setup_logging(verbose=verbosity == VerbosityLevel.VERBOSE)

    print_banner()

    with startup_spinner("Checking permissions..."):
        permissions_ok = check_and_request_permissions()

    if not permissions_ok:
        print_startup_step("Permissions denied", success=False)
        console.print(f"  [{THEME['error']}]Cannot proceed without permissions[/]")
        sys.exit(1)

    print_startup_step("Permissions granted")

    with startup_spinner("Detecting platform..."):
        capabilities = detect_platform()

    print_platform_info(capabilities)

    from .config.llm_config import LLMConfig
    from .services.twilio_service import TwilioService
    from .services.webhook_server import WebhookServer

    with startup_spinner("Initializing services..."):
        twilio_service = TwilioService()
        twilio_service.set_llm_client(LLMConfig.get_llm())

        webhook_server = None
        if twilio_service.is_configured():
            webhook_server = WebhookServer(twilio_service)
            webhook_server.start()

    with startup_spinner("Loading tools..."):
        crew = ComputerUseCrew(
            capabilities,
            SafetyChecker(),
            confirmation_manager=CommandConfirmation(),
            use_browser_profile=use_browser_profile,
            browser_profile_directory=browser_profile,
        )

    tool_count = len(crew.tool_registry.list_available_tools())
    print_startup_step(f"{tool_count} tools loaded")

    system_status = {
        "Tools": str(tool_count),
        "Webhook": f":{webhook_server.port}" if webhook_server else "off",
        "Browser": browser_profile if use_browser_profile else "default",
    }
    print_status_overview("System", system_status)

    print_ready()

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
                    console.print(f"\n  [{THEME['muted']}]Goodbye[/]")
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
                            ActionType.ERROR,
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
                    console.print(f"\n  [{THEME['warning']}]Task cancelled[/]\n")

            except KeyboardInterrupt:
                dashboard.stop_dashboard()
                console.print(f"\n\n  [{THEME['muted']}]Interrupted[/]")
                break
            except asyncio.CancelledError:
                dashboard.stop_dashboard()
                console.print(f"  [{THEME['warning']}]Task cancelled[/]\n")
                continue
            except Exception as e:
                dashboard.stop_dashboard()
                console.print(f"\n  [{THEME['error']}]Error: {e}[/]")
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
        console.print(f"\n\n  [{THEME['muted']}]Goodbye[/]")


if __name__ == "__main__":
    cli()
