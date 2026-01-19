#!/usr/bin/env python3
"""Interactive CLI for testing the chat agent with full database connectivity."""

import sys
import os
from typing import Optional

# Add parent directory to path for imports
bin_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(bin_dir)
sys.path.insert(0, backend_dir)

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv

# Load CLI-specific .env from bin directory (uses localhost for DB connections)
# Falls back to backend/.env if bin/.env doesn't exist
# IMPORTANT: We must set env vars BEFORE importing modules that use Pydantic settings,
# because they read from .env file directly at import time
cli_env_path = os.path.join(bin_dir, ".env")
using_cli_env = os.path.exists(cli_env_path)
if using_cli_env:
    # Load into os.environ so Pydantic settings will pick them up
    from dotenv import dotenv_values
    cli_env_values = dotenv_values(cli_env_path)
    for key, value in cli_env_values.items():
        if value is not None:
            os.environ[key] = value
    load_dotenv(cli_env_path, override=True)
else:
    # Fall back to backend/.env (Docker hostnames - will fail outside container)
    load_dotenv(os.path.join(backend_dir, ".env"), override=True)

# NOTE: agents module is imported lazily inside commands to allow --build to set
# AGENT_BUILD env var before the module initializes its singleton build instance

app = typer.Typer(help="Interactive CLI for testing the chat agent")
console = Console()


def _get_available_builds() -> list:
    """Get list of available agent builds without initializing the singleton."""
    from agents.builds import list_builds
    return list_builds()


@app.command("list-builds")
def list_builds_cmd():
    """List available agent builds."""
    builds = _get_available_builds()
    current = os.environ.get("AGENT_BUILD", "v1")

    table = Table(title="Available Agent Builds")
    table.add_column("Build", style="cyan")
    table.add_column("Status")

    for build in builds:
        status = "[green]active[/]" if build == current else ""
        table.add_row(build, status)

    console.print(table)
    console.print(f"\n[dim]Default build: v1[/]")
    console.print(f"[dim]Use --build <name> to select a different build[/]")


@app.command()
def chat(
    scopes: str = typer.Option(
        "global:admin",
        "--scopes", "-s",
        help="Comma-separated scopes (e.g., 'macro:analyst,equity:reader')"
    ),
    topic: Optional[str] = typer.Option(
        None,
        "--topic", "-t",
        help="Initial topic context"
    ),
    section: str = typer.Option(
        "home",
        "--section",
        help="Initial section (home, reader, analyst, editor, admin)"
    ),
    user_id: int = typer.Option(
        1,
        "--user-id",
        help="Mock user ID"
    ),
    name: str = typer.Option(
        "CLI User",
        "--name", "-n",
        help="Display name for the test user"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show detailed response info (UI actions, articles, etc.)"
    ),
    build: Optional[str] = typer.Option(
        None,
        "--build", "-b",
        help="Agent build version to use (e.g., 'v1'). Use 'list-builds' to see available builds."
    ),
):
    """Start interactive chat session with the agent."""

    # Set agent build if specified (must happen before importing agents module)
    available_builds = _get_available_builds()
    if build:
        if build not in available_builds:
            console.print(f"[red]Error:[/] Unknown build '{build}'")
            console.print(f"[dim]Available builds: {', '.join(available_builds)}[/]")
            raise typer.Exit(1)
        os.environ["AGENT_BUILD"] = build

    # Get the active build name (either specified or default)
    active_build = os.environ.get("AGENT_BUILD", "v1")

    # Now import agents module (after AGENT_BUILD is set)
    from database import SessionLocal
    from agents import invoke_chat, create_user_context, create_navigation_context

    # Check which .env file is being used
    if not using_cli_env:
        console.print(Panel(
            "[yellow]WARNING:[/] No bin/.env file found.\n\n"
            "Using backend/.env which has Docker hostnames.\n"
            "This will fail if running outside Docker.\n\n"
            "To fix, create bin/.env:\n"
            "  [dim]cp bin/.env.example bin/.env[/]\n"
            "  [dim]# Edit bin/.env with your OPENAI_API_KEY[/]",
            title="Configuration",
            border_style="yellow"
        ))

    # Debug: show connection settings
    if verbose:
        console.print(f"[dim]DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}[/]")
        console.print(f"[dim]REDIS_URL: {os.environ.get('REDIS_URL', 'NOT SET')}[/]")
        console.print(f"[dim]CHROMA_HOST: {os.environ.get('CHROMA_HOST', 'NOT SET')}[/]")
        console.print(f"[dim]CHROMA_PORT: {os.environ.get('CHROMA_PORT', 'NOT SET')}[/]")

    # Create database session
    db = SessionLocal()

    try:
        # Create user context
        scope_list = [s.strip() for s in scopes.split(",")]
        user_context = create_user_context(
            user_id=user_id,
            email="cli@test.local",
            name=name,
            scopes=scope_list,
        )

        # Create navigation context
        nav_context = create_navigation_context(
            section=section,
            topic=topic,
        )

        # Show startup info
        env_source = "bin/.env" if using_cli_env else "backend/.env"
        console.print(Panel(
            f"[bold]User:[/] {name}\n"
            f"[bold]Scopes:[/] {scopes}\n"
            f"[bold]Topic:[/] {topic or 'none'}\n"
            f"[bold]Build:[/] {active_build}\n"
            f"[bold]Config:[/] {env_source}\n"
            f"[bold]Database:[/] Connected",
            title="Chat Agent CLI",
            border_style="green"
        ))
        console.print("[dim]Type 'quit' to exit, 'help' for commands[/]\n")

        # REPL loop
        while True:
            try:
                message = console.input("[bold green]You:[/] ").strip()

                if not message:
                    continue

                if message.lower() in ("quit", "exit"):
                    console.print("Goodbye!")
                    break

                if message.lower() == "help":
                    _show_help()
                    continue

                if message.lower() == "context":
                    _show_context(user_context, nav_context)
                    continue

                if message.lower() == "clear":
                    _clear_history(user_id)
                    continue

                if message.lower() == "build":
                    console.print(f"[dim]Current agent build: {active_build}[/]")
                    console.print(f"[dim]Available builds: {', '.join(available_builds)}[/]")
                    continue

                if message.startswith("/topic "):
                    new_topic = message[7:].strip()
                    nav_context = create_navigation_context(
                        section=nav_context.get("section", "home"),
                        topic=new_topic if new_topic else None,
                    )
                    console.print(f"[dim]Topic set to: {new_topic or 'none'}[/]")
                    continue

                if message.startswith("/section "):
                    new_section = message[9:].strip()
                    nav_context = create_navigation_context(
                        section=new_section,
                        topic=nav_context.get("topic"),
                    )
                    console.print(f"[dim]Section set to: {new_section}[/]")
                    continue

                # Invoke chat agent
                with console.status("[bold blue]Thinking...[/]"):
                    response = invoke_chat(
                        message=message,
                        user_context=user_context,
                        navigation_context=nav_context,
                    )

                # Display response
                console.print(Panel(
                    Markdown(response.response),
                    title=f"[bold cyan]Agent: {response.agent_type}[/]",
                    subtitle=f"[dim]{response.routing_reason}[/]",
                    border_style="cyan"
                ))

                # Show extra info in verbose mode
                if verbose:
                    if response.articles:
                        console.print(f"[dim]Articles referenced: {len(response.articles)}[/]")
                    if response.ui_action:
                        console.print(f"[dim]UI Action: {response.ui_action}[/]")
                    if response.navigation:
                        console.print(f"[dim]Navigation: {response.navigation}[/]")
                    if response.editor_content:
                        console.print(f"[dim]Editor content provided[/]")
                    if response.confirmation:
                        console.print(f"[yellow]Confirmation required: {response.confirmation}[/]")

                console.print()  # Blank line for readability

            except KeyboardInterrupt:
                console.print("\n[dim]Use 'quit' to exit[/]")
                continue
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")
                if verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/]")

    finally:
        db.close()


def _show_help():
    """Display help information."""
    table = Table(title="Commands")
    table.add_column("Command", style="cyan")
    table.add_column("Description")
    table.add_row("quit / exit", "Exit the CLI")
    table.add_row("help", "Show this help")
    table.add_row("context", "Show current user and navigation context")
    table.add_row("clear", "Clear conversation history")
    table.add_row("build", "Show current agent build version")
    table.add_row("/topic <name>", "Change topic context (empty to clear)")
    table.add_row("/section <name>", "Change section context")
    console.print(table)
    console.print()


def _show_context(user_context, nav_context):
    """Display current context."""
    console.print(Panel(
        f"[bold]User Context:[/]\n"
        f"  user_id: {user_context.get('user_id')}\n"
        f"  name: {user_context.get('name')}\n"
        f"  email: {user_context.get('email')}\n"
        f"  scopes: {user_context.get('scopes')}\n"
        f"  highest_role: {user_context.get('highest_role')}\n"
        f"  topic_roles: {user_context.get('topic_roles')}\n\n"
        f"[bold]Navigation Context:[/]\n"
        f"  section: {nav_context.get('section')}\n"
        f"  topic: {nav_context.get('topic')}\n"
        f"  role: {nav_context.get('role')}",
        title="Current Context"
    ))
    console.print()


def _clear_history(user_id: int):
    """Clear conversation history for the user."""
    try:
        from conversation_memory import clear_conversation_history
        clear_conversation_history(user_id)
        console.print("[dim]Conversation history cleared[/]")
    except Exception as e:
        console.print(f"[yellow]Could not clear history: {e}[/]")
    console.print()


if __name__ == "__main__":
    app()
