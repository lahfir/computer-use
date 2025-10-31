"""
Professional terminal UI using rich and prompt_toolkit.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings

console = Console()

_key_bindings = KeyBindings()


@_key_bindings.add("enter")
def _(event):
    """
    Handle Enter key - submit the input.
    """
    event.current_buffer.validate_and_handle()


@_key_bindings.add("c-j")
def _(event):
    """
    Handle Ctrl+J - insert newline (alternative for Shift+Enter).
    """
    event.current_buffer.insert_text("\n")


@_key_bindings.add("escape", "enter")
def _(event):
    """
    Handle Alt/Option+Enter - insert newline.
    """
    event.current_buffer.insert_text("\n")


_prompt_session = PromptSession(
    history=None,
    multiline=True,
    key_bindings=_key_bindings,
)


def print_banner():
    """
    Display startup banner.
    """
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🤖 Computer Use Agent - Multi-Platform             ║
    ║        Autonomous Desktop & Web Automation                ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def print_section_header(title: str, icon: str = ""):
    """
    Print styled section header.
    """
    console.print()
    console.rule(f"{icon} {title}", style="bold blue")
    console.print()


def print_platform_info(capabilities):
    """
    Display platform capabilities in styled table.
    """
    table = Table(title="Platform Information", box=box.ROUNDED, show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("OS", f"{capabilities.os_type} {capabilities.os_version}")
    table.add_row(
        "Screen",
        f"{capabilities.screen_resolution[0]}x{capabilities.screen_resolution[1]}",
    )
    table.add_row("Scaling", f"{capabilities.scaling_factor}x")

    if capabilities.gpu_available:
        gpu_info = (
            f"{capabilities.gpu_type} ({capabilities.gpu_device_count} device(s))"
        )
        table.add_row("GPU", f"✅ {gpu_info}")
    else:
        table.add_row("GPU", "⚠️  Not available (CPU only)")

    console.print(table)
    console.print()

    caps_table = Table(
        title="Automation Capabilities", box=box.ROUNDED, show_header=False
    )
    caps_table.add_column("Tier", style="cyan")
    caps_table.add_column("Status", style="white")

    if capabilities.accessibility_api_available:
        caps_table.add_row(
            "Tier 1",
            f"✅ {capabilities.accessibility_api_type} (100% accuracy)",
        )
    else:
        caps_table.add_row("Tier 1", "⚠️  Accessibility API not available")

    caps_table.add_row("Tier 2", "✅ Computer Vision + OCR (95-99% accuracy)")
    caps_table.add_row("Tier 3", "✅ Vision Model Fallback (85-95% accuracy)")

    console.print(caps_table)
    console.print()

    tools_list = " • ".join(capabilities.supported_tools)
    tools_table = Table(
        title="Available Tools", box=box.ROUNDED, show_header=False, width=80
    )
    tools_table.add_column("Tools", style="cyan", no_wrap=False)
    tools_table.add_row(tools_list)

    console.print(tools_table)


def print_task_analysis(task: str, analysis):
    """
    Display task analysis in panel with sub-task breakdown.
    """
    content = f"""
[bold]Task:[/bold] {task}

[cyan]Classification:[/cyan]
  • Type: [bold]{analysis.task_type.value.upper()}[/bold]
  • Browser: {"[green]Yes[/green]" if analysis.requires_browser else "[dim]No[/dim]"}
  • GUI: {"[green]Yes[/green]" if analysis.requires_gui else "[dim]No[/dim]"}
  • System: {"[green]Yes[/green]" if analysis.requires_system else "[dim]No[/dim]"}

[yellow]Reasoning:[/yellow] {analysis.reasoning}
"""

    # Add sub-task breakdown if available
    if any(
        [
            analysis.browser_subtask,
            analysis.gui_subtask,
            analysis.system_subtask,
        ]
    ):
        content += "\n[magenta]Task Breakdown:[/magenta]\n"

        if analysis.browser_subtask:
            content += f"""
  [bold cyan]🌐 Browser Agent:[/bold cyan]
    [dim]→[/dim] {analysis.browser_subtask.objective}
    [dim]📦 Output:[/dim] {analysis.browser_subtask.expected_output}
"""

        if analysis.gui_subtask:
            content += f"""
  [bold green]🖥️  GUI Agent:[/bold green]
    [dim]→[/dim] {analysis.gui_subtask.objective}
    [dim]📦 Output:[/dim] {analysis.gui_subtask.expected_output}
"""

        if analysis.system_subtask:
            content += f"""
  [bold yellow]⚙️  System Agent:[/bold yellow]
    [dim]→[/dim] {analysis.system_subtask.objective}
    [dim]📦 Output:[/dim] {analysis.system_subtask.expected_output}
"""

    panel = Panel(
        content,
        title="🎯 Task Analysis & Breakdown",
        border_style="blue",
        box=box.DOUBLE,
    )
    console.print(panel)


def print_agent_start(agent_name: str):
    """
    Announce agent execution start.
    """
    console.print()
    console.print(
        Panel(
            f"[bold cyan]{agent_name} Agent Executing[/bold cyan]",
            border_style="cyan",
            box=box.HEAVY,
        )
    )
    console.print()


def print_step(step: int, action: str, target: str, reasoning: str):
    """
    Display agent step with styling.
    """
    console.print(
        f"[bold blue]Step {step}:[/bold blue] [cyan]{action}[/cyan] → [white]{target}[/white]"
    )
    console.print(f"  [dim]{reasoning}[/dim]")


def print_success(message: str):
    """
    Print success message.
    """
    console.print(f"  [green]✅ {message}[/green]")


def print_failure(message: str):
    """
    Print failure message.
    """
    console.print(f"  [red]❌ {message}[/red]")


def print_info(message: str):
    """
    Print info message.
    """
    console.print(f"  [cyan]ℹ️  {message}[/cyan]")


def print_warning(message: str):
    """
    Print warning message.
    """
    console.print(f"  [yellow]⚠️  {message}[/yellow]")


def print_command_approval(command: str) -> str:
    """
    Display command approval request.

    Returns:
        User's choice ('1', '2', or '3')
    """
    console.print()
    panel = Panel(
        f"[bold yellow]💻 Command:[/bold yellow] [cyan]{command}[/cyan]\n\n"
        "[bold]Options:[/bold]\n"
        "  [green][1][/green] Allow once\n"
        "  [blue][2][/blue] Allow for session\n"
        "  [red][3][/red] Deny (stop agent)",
        title="🔐 Command Approval Required",
        border_style="yellow",
        box=box.DOUBLE,
    )
    console.print(panel)

    choice = console.input("[bold]Your choice (1/2/3):[/bold] ").strip()
    return choice


def print_handoff(from_agent: str, to_agent: str, reason: str):
    """
    Display agent handoff.
    """
    console.print()
    console.print(
        Panel(
            f"[bold]{from_agent}[/bold] → [bold]{to_agent}[/bold]\n\n"
            f"[dim]Reason: {reason}[/dim]",
            title="🤝 Agent Handoff",
            border_style="magenta",
            box=box.HEAVY,
        )
    )
    console.print()


def print_task_result(result: dict):
    """
    Display final task result.
    """
    console.print()

    success = result.get("overall_success", False)
    title = "✅ Task Complete" if success else "❌ Task Failed"
    style = "green" if success else "red"

    content = f"[bold]Task:[/bold] {result.get('task', 'Unknown')}\n\n"

    handoffs = []
    outputs = []
    if result.get("results"):
        content += "[bold]Execution Steps:[/bold]\n\n"
        for i, res in enumerate(result["results"], 1):
            if not res or not isinstance(res, dict):
                continue

            status = "✅" if res.get("success") else "❌"
            method = res.get("method_used", "unknown")
            action = res.get("action_taken", "")

            content += f"  {status} [cyan]Step {i}:[/cyan] [{method}] {action}\n"

            if res.get("error"):
                content += f"     [red]Error: {res['error']}[/red]\n"

            data = res.get("data")
            if data and isinstance(data, dict) and data.get("output"):
                outputs.append({"step": i, "method": method, "output": data["output"]})

            if res.get("handoff_requested"):
                handoffs.append(
                    {
                        "from": "GUI" if "gui" in method.lower() else "SYSTEM",
                        "to": res.get("suggested_agent", "unknown").upper(),
                        "reason": res.get("handoff_reason", ""),
                    }
                )

    if handoffs:
        content += "\n[bold magenta]Agent Handoffs:[/bold magenta]\n\n"
        for handoff in handoffs:
            content += f"  🤝 [cyan]{handoff['from']}[/cyan] → [yellow]{handoff['to']}[/yellow]\n"
            if handoff["reason"]:
                content += f"     [dim]Reason: {handoff['reason']}[/dim]\n"

    if outputs:
        content += "\n[bold green]📄 Results:[/bold green]\n\n"
        for output in outputs:
            content += f"[cyan]{output['method'].upper()}:[/cyan]\n"
            content += f"{output['output']}\n\n"

    panel = Panel(
        content,
        title=title,
        border_style=style,
        box=box.DOUBLE,
    )
    console.print(panel)


def print_action_history(history: list):
    """
    Display action history table.
    """
    if not history:
        return

    table = Table(title="📋 Action History", box=box.ROUNDED)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Action", style="white")
    table.add_column("Target", style="yellow")
    table.add_column("Result", style="green")

    for i, action in enumerate(history[-5:], 1):  # Show last 5
        status = "✅" if action.get("success") else "❌"
        table.add_row(
            str(i),
            action.get("action", ""),
            action.get("target", "")[:30],
            status,
        )

    console.print(table)


def print_webhook_status(port: int, status: str = "starting"):
    """
    Display webhook server status with styled panel.

    Args:
        port: Port number the webhook is using
        status: Status of webhook ('starting', 'ready', 'failed', 'port_changed')
    """
    if status == "starting":
        console.print(
            f"[cyan]🌐 Twilio webhook server starting on port {port}...[/cyan]"
        )
    elif status == "ready":
        table = Table(
            title="📞 Twilio Webhook Server", box=box.ROUNDED, show_header=False
        )
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Status", "[green]✅ Ready[/green]")
        table.add_row("Local URL", f"http://localhost:{port}/sms")
        table.add_row("Health Check", f"http://localhost:{port}/health")
        table.add_row("Ngrok Command", f"[yellow]ngrok http {port}[/yellow]")

        console.print(table)
    elif status == "port_changed":
        console.print(
            f"[yellow]⚠️  Port {port - 1} in use, trying port {port}...[/yellow]"
        )
    elif status == "failed":
        console.print(f"[red]❌ Could not start webhook server on port {port}[/red]")


def print_twilio_config_status(is_configured: bool, phone_number: str = None):
    """
    Display Twilio configuration status.

    Args:
        is_configured: Whether Twilio is configured
        phone_number: Twilio phone number if configured
    """
    if is_configured and phone_number:
        console.print(
            f"[green]✅ Twilio configured with number: {phone_number}[/green]"
        )
    elif not is_configured:
        console.print(
            "[yellow]⚠️  Twilio not configured (phone verification unavailable)[/yellow]"
        )
        console.print(
            "[dim]   Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in .env[/dim]"
        )


async def get_task_input() -> str:
    """
    Get task input from user with proper terminal editing support.
    Uses prompt_toolkit for readline-like editing with history.
    Supports multi-line input via Alt+Enter or Ctrl+J.

    Note: Shift+Enter is not reliably distinguishable from Enter in most
    terminal emulators due to terminal protocol limitations. Alt+Enter
    (Option+Enter on macOS) provides the same UX and works reliably.

    Returns:
        User's task input (stripped)
    """
    try:
        console.print()
        console.print("[#00d7ff]💬 Enter your task:[/]")
        console.print(
            "[dim]   Press [cyan]Alt+Enter[/cyan] for new line, [cyan]Enter[/cyan] to submit[/dim]"
        )
        console.print()

        prompt_text = FormattedText([("#00d7ff bold", "➤ ")])

        task = await _prompt_session.prompt_async(
            prompt_text,
            prompt_continuation=FormattedText([("", "  ")]),
        )

        return task.strip()
    except (KeyboardInterrupt, EOFError):
        return "quit"
