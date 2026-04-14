"""CLI entry point."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from hwarang_cli import __version__

app = typer.Typer(
    name="hwarang",
    help="Hwarang AI Agent - Terminal AI assistant",
    no_args_is_help=True,
)
console = Console()


@app.command()
def chat(
    provider: str = typer.Option("hwarang", "--provider", "-p", help="LLM provider"),
    model: str = typer.Option("", "--model", "-m", help="Model name"),
    api_url: str = typer.Option("", "--api-url", help="API server URL"),
    temperature: float = typer.Option(0.7, "--temperature", "-t", help="Sampling temperature"),
    system: str = typer.Option("", "--system", "-s", help="System prompt"),
):
    """Start interactive AI agent session."""
    from hwarang_cli.config import CLIConfig
    from hwarang_cli.repl import run_repl

    config = CLIConfig.load()

    # Override config with CLI args
    if provider:
        config.default_provider = provider
    if model:
        config.default_model = model
    if api_url:
        config.hwarang_api_url = api_url
    config.temperature = temperature

    asyncio.run(run_repl(config, system_prompt=system or None))


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Prompt to send"),
    provider: str = typer.Option("hwarang", "--provider", "-p"),
    model: str = typer.Option("", "--model", "-m"),
    api_url: str = typer.Option("", "--api-url"),
):
    """Run a single prompt non-interactively."""
    from hwarang_cli.config import CLIConfig
    from hwarang_cli.providers import create_provider

    config = CLIConfig.load()
    if provider:
        config.default_provider = provider
    if model:
        config.default_model = model
    if api_url:
        config.hwarang_api_url = api_url

    async def _run():
        llm = create_provider(config)
        response = await llm.chat(
            messages=[{"role": "user", "content": prompt}],
            model=config.default_model,
        )
        console.print(response.content)

    asyncio.run(_run())


@app.command()
def version():
    """Show version."""
    console.print(f"Hwarang CLI v{__version__}")


@app.command()
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Show current config"),
    init: bool = typer.Option(False, "--init", help="Create default config file"),
):
    """Manage CLI configuration."""
    from hwarang_cli.config import CLIConfig

    if init:
        config = CLIConfig()
        config.save()
        console.print(f"Config created at {CLIConfig.config_path()}")
    elif show:
        config = CLIConfig.load()
        from dataclasses import asdict

        for key, value in asdict(config).items():
            if "key" in key.lower() and value:
                value = value[:8] + "..."
            console.print(f"  {key}: {value}")


if __name__ == "__main__":
    app()
