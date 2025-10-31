"""
Main entry point for computer use automation agent.
"""

import asyncio
import sys
from .utils.platform_detector import detect_platform
from .utils.safety_checker import SafetyChecker
from .utils.command_confirmation import CommandConfirmation
from .utils.permissions import check_and_request_permissions
from .utils.logging_config import setup_logging
from .utils.ui import (
    print_banner,
    print_platform_info,
    print_section_header,
    print_task_result,
    get_task_input,
    console,
)
from .crew import ComputerUseCrew


async def main():
    """
    Main execution function.
    """
    import logging
    import warnings
    import os

    warnings.filterwarnings("ignore")
    os.environ["PPOCR_SHOW_LOG"] = "False"

    for logger_name in ["browser_use", "easyocr", "paddleocr", "werkzeug", "flask"]:
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)
        logging.getLogger(logger_name).propagate = False

    setup_logging()

    print_banner()

    if not check_and_request_permissions():
        console.print("[yellow]Exiting due to missing permissions.[/yellow]")
        sys.exit(1)

    print_section_header("Platform Detection", "🔍")
    capabilities = detect_platform()
    print_platform_info(capabilities)

    print_section_header("Initializing Systems", "🚀")

    from .services.twilio_service import TwilioService
    from .services.webhook_server import WebhookServer
    from .utils.ui import print_twilio_config_status
    from .config.llm_config import LLMConfig

    twilio_service = TwilioService()
    twilio_service.set_llm_client(LLMConfig.get_llm())

    if twilio_service.is_configured():
        print_twilio_config_status(True, twilio_service.get_phone_number())
        webhook_server = WebhookServer(twilio_service)
        webhook_server.start()
    else:
        print_twilio_config_status(False)
        webhook_server = None

    crew = ComputerUseCrew(
        capabilities,
        SafetyChecker(),
        confirmation_manager=CommandConfirmation(),
        twilio_service=twilio_service,
    )

    console.print(
        f"[green]✅ Loaded {len(crew.tool_registry.list_available_tools())} tools[/green]"
    )
    console.print("[green]✅ Crew initialized successfully[/green]")

    print_section_header("Ready for Automation", "✨")

    while True:
        try:
            task = await get_task_input()

            if not task:
                continue

            if task.lower() in ["quit", "exit", "q"]:
                console.print("\n[bold cyan]👋 Goodbye![/bold cyan]")
                break

            console.print(
                f"\n[bold yellow]⏳ Processing:[/bold yellow] [white]{task}[/white]"
            )
            result = await crew.execute_task(task)

            print_task_result(result)

        except KeyboardInterrupt:
            console.print("\n\n[yellow]⚠️  Interrupted by user[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]❌ Error: {e}[/red]")
            import traceback

            traceback.print_exc()


def cli():
    """
    CLI entry point.
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n[bold cyan]👋 Goodbye![/bold cyan]")


if __name__ == "__main__":
    cli()
