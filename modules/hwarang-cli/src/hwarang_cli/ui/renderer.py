"""Rich-based terminal rendering utilities."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table


console = Console()


def render_markdown(text: str) -> None:
    """Render markdown text in the terminal."""
    md = Markdown(text)
    console.print(md)


def render_code(code: str, language: str = "python") -> None:
    """Render syntax-highlighted code."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def render_error(message: str) -> None:
    """Render an error message."""
    console.print(Panel(message, title="Error", border_style="red"))


def render_tool_call(tool_name: str, arguments: str, result: str) -> None:
    """Render a tool call and its result."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("[bold yellow]Tool:[/bold yellow]", tool_name)
    table.add_row("[dim]Args:[/dim]", arguments[:200])
    console.print(table)
    if result:
        console.print(Panel(result[:500], border_style="dim", title="Result"))


def render_token_usage(prompt_tokens: int, completion_tokens: int) -> None:
    """Render token usage information."""
    total = prompt_tokens + completion_tokens
    console.print(
        f"[dim]Tokens: {prompt_tokens} prompt + {completion_tokens} completion = {total} total[/dim]"
    )
