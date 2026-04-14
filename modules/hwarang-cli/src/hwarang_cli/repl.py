"""Interactive REPL for the Hwarang CLI."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

from hwarang_cli.agent.agent import Agent
from hwarang_cli.config import CLIConfig
from hwarang_cli.providers import create_provider
from hwarang_cli.tools.registry import ToolRegistry

console = Console(
    theme=Theme({
        "user": "bold cyan",
        "assistant": "bold green",
        "tool": "bold yellow",
        "error": "bold red",
    })
)


async def run_repl(config: CLIConfig, system_prompt: str | None = None) -> None:
    """Run the interactive REPL."""
    # Setup
    provider = create_provider(config)
    tool_registry = ToolRegistry()
    tool_registry.register_defaults()

    agent = Agent(
        provider=provider,
        tool_registry=tool_registry,
        model=config.default_model,
        system_prompt=system_prompt,
        temperature=config.temperature,
    )

    # Welcome message
    console.print(
        Panel(
            f"[bold]Hwarang AI Agent[/bold]\n"
            f"Provider: {config.default_provider} | Model: {config.default_model}\n"
            f"Tools: {', '.join(tool_registry.tool_names)}\n"
            f"Type [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit",
            title="화랑 (Hwarang)",
            border_style="cyan",
        )
    )

    while True:
        try:
            # Get user input
            console.print()
            user_input = console.input("[user]You>[/user] ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                handled = _handle_command(user_input, agent, config)
                if handled == "quit":
                    break
                continue

            # Process with agent
            console.print()
            console.print("[assistant]Hwarang>[/assistant] ", end="")

            try:
                # Try streaming first
                full_response = ""
                async for chunk in agent.stream_run(user_input):
                    console.print(chunk, end="")
                    full_response += chunk
                console.print()

            except Exception:
                # Fall back to non-streaming
                response = await agent.run(user_input)
                console.print(Markdown(response))

        except KeyboardInterrupt:
            console.print("\n[dim]Use /quit to exit[/dim]")
            continue
        except EOFError:
            break

    console.print("\n[dim]Goodbye![/dim]")


def _handle_command(command: str, agent: Agent, config: CLIConfig) -> str | None:
    """Handle slash commands. Returns 'quit' to exit."""
    cmd = command.lower().split()[0]

    if cmd in ("/quit", "/exit", "/q"):
        return "quit"

    elif cmd == "/help":
        console.print(Panel(
            "/help     - Show this help\n"
            "/quit     - Exit the REPL\n"
            "/clear    - Clear conversation history\n"
            "/tools    - List available tools\n"
            "/model    - Show current model info\n"
            "/history  - Show conversation stats",
            title="Commands",
        ))

    elif cmd == "/clear":
        agent.context.clear()
        console.print("[dim]Conversation cleared[/dim]")

    elif cmd == "/tools":
        for tool_def in agent.tools.get_tool_definitions():
            func = tool_def["function"]
            console.print(f"  [bold]{func['name']}[/bold] - {func['description']}")

    elif cmd == "/model":
        console.print(f"  Provider: {config.default_provider}")
        console.print(f"  Model: {config.default_model}")
        console.print(f"  Temperature: {config.temperature}")

    elif cmd == "/history":
        console.print(f"  Messages: {agent.context.num_messages}")

    else:
        console.print(f"[error]Unknown command: {cmd}[/error]")

    return None
