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
from .utils.task_stop_handler import TaskStopHandler
from .utils.ui import (
    print_task_result,
    print_platform_info,
    print_section_header,
    console,
    print_info,
)
from .crew import ComputerUseCrew


async def main():
    """
    Main execution function.
    """
    setup_logging()

    console.print("\n[bold cyan]🤖 Computer Use Agent[/bold cyan]")
    console.print()

    if not check_and_request_permissions():
        console.print("[yellow]Exiting due to missing permissions.[/yellow]")
        sys.exit(1)

    print_section_header("Platform Detection")
    console.print()
    capabilities = detect_platform()
    print_platform_info(capabilities)

    print_section_header("Initializing Systems")
    console.print()
    print_info("Safety Checker")
    safety_checker = SafetyChecker()

    print_info("Command Confirmation System")
    confirmation_manager = CommandConfirmation()

    print_info("Task Stop Handler (ESC support)")
    stop_handler = TaskStopHandler()

    print_info("AI Agents & Tool Registry")
    crew = ComputerUseCrew(
        capabilities,
        safety_checker,
        confirmation_manager=confirmation_manager,
        stop_handler=stop_handler,
    )

    console.print(
        f"[green]✅ Ready[/green] ({capabilities.os_type}, {len(crew.tool_registry.list_available_tools())} tools)"
    )
    console.print("[dim]Press ESC during task execution to stop[/dim]")
    console.print()

    while True:
        try:
            task = console.input(
                "\n[bold cyan]💬 Enter task (or 'quit' to exit):[/bold cyan] "
            ).strip()

            if not task:
                continue

            if task.lower() in ["quit", "exit", "q"]:
                console.print("\n[bold cyan]👋 Goodbye![/bold cyan]")
                break

            stop_handler.reset()
            stop_handler.start_listening()

            try:
                result = await crew.execute_task(task)
                print_task_result(result)
            finally:
                stop_handler.stop_listening()

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
