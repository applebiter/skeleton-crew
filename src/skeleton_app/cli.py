"""Command-line interface for skeleton-app."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel

from skeleton_app.config import Config, EnvSettings
from skeleton_app.core.types import LLMMessage, LLMRequest
from skeleton_app.providers.llm import AnthropicProvider, OllamaProvider, OpenAIProvider
from skeleton_app.db_commands import db
from skeleton_app.cluster_commands import cluster

console = Console()


def setup_logging(level: str = "INFO"):
    """Set up logging with rich handler."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)]
    )


@click.group()
@click.option("--config", type=click.Path(exists=True), help="Path to config file")
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def cli(ctx, config: Optional[str], log_level: str):
    """Skeleton App - Distributed voice/agent system."""
    ctx.ensure_object(dict)
    
    setup_logging(log_level)
    
    # Load configuration
    if config:
        config_path = Path(config)
    else:
        config_path = Path("config.yaml")
        if not config_path.exists():
            config_path = Path("config.example.yaml")
    
    if config_path.exists():
        ctx.obj["config"] = Config.from_yaml(config_path)
    else:
        ctx.obj["config"] = None
    
    # Load environment settings
    ctx.obj["env"] = EnvSettings()


# Add database commands
cli.add_command(db)

# Add cluster commands
cli.add_command(cluster)


@cli.command()
@click.pass_context
def repl(ctx):
    """Start an interactive REPL for testing."""
    asyncio.run(run_repl(ctx.obj))


async def run_repl(context: dict):
    """Run the interactive REPL."""
    env = context["env"]
    config = context.get("config")
    
    console.print(Panel.fit(
        "[bold cyan]Skeleton App REPL[/bold cyan]\n"
        "Type your messages to chat with the LLM.\n"
        "Commands: /quit, /clear, /model <name>, /stream, /help",
        border_style="cyan"
    ))
    
    # Initialize LLM provider
    provider = None
    streaming = False
    
    # Try Ollama first
    try:
        ollama = OllamaProvider(
            base_url=env.ollama_host,
            default_model="llama3.2:3b"
        )
        models = await ollama.list_models()
        if models:
            provider = ollama
            console.print(f"[green]✓[/green] Connected to Ollama ({len(models)} models available)")
        else:
            await ollama.close()
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Ollama not available: {e}")
    
    # Fallback to OpenAI
    if not provider and env.openai_api_key:
        try:
            provider = OpenAIProvider(
                api_key=env.openai_api_key,
                default_model="gpt-4o-mini"
            )
            console.print("[green]✓[/green] Using OpenAI API")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] OpenAI not available: {e}")
    
    # Fallback to Anthropic
    if not provider and env.anthropic_api_key:
        try:
            provider = AnthropicProvider(
                api_key=env.anthropic_api_key,
                default_model="claude-3-5-sonnet-20241022"
            )
            console.print("[green]✓[/green] Using Anthropic API")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Anthropic not available: {e}")
    
    if not provider:
        console.print("[red]✗[/red] No LLM provider available. Please configure Ollama or add API keys to .env")
        return
    
    # Conversation history
    messages = []
    
    try:
        while True:
            try:
                user_input = console.input("\n[bold cyan]You:[/bold cyan] ")
                
                if not user_input.strip():
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    command = user_input[1:].strip().split()
                    cmd = command[0].lower()
                    
                    if cmd == "quit" or cmd == "exit":
                        break
                    elif cmd == "clear":
                        messages = []
                        console.print("[green]Conversation cleared[/green]")
                        continue
                    elif cmd == "stream":
                        streaming = not streaming
                        console.print(f"[green]Streaming {'enabled' if streaming else 'disabled'}[/green]")
                        continue
                    elif cmd == "model":
                        if len(command) > 1:
                            model_name = command[1]
                            console.print(f"[green]Model set to: {model_name}[/green]")
                        else:
                            console.print("[yellow]Usage: /model <name>[/yellow]")
                        continue
                    elif cmd == "help":
                        console.print(Panel(
                            "/quit, /exit - Exit the REPL\n"
                            "/clear - Clear conversation history\n"
                            "/stream - Toggle streaming mode\n"
                            "/model <name> - Change model\n"
                            "/help - Show this help",
                            title="Commands",
                            border_style="blue"
                        ))
                        continue
                    else:
                        console.print(f"[red]Unknown command: {cmd}[/red]")
                        continue
                
                # Add user message
                messages.append(LLMMessage(role="user", content=user_input))
                
                # Create request
                request = LLMRequest(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048
                )
                
                # Get response
                console.print("\n[bold green]Assistant:[/bold green] ", end="")
                
                if streaming:
                    # Streaming response
                    response_text = ""
                    async for chunk in provider.chat_stream(request):
                        console.print(chunk, end="")
                        response_text += chunk
                    console.print()  # New line after streaming
                    
                    # Add to history
                    messages.append(LLMMessage(role="assistant", content=response_text))
                else:
                    # Non-streaming response
                    response = await provider.chat(request)
                    console.print(Markdown(response.content))
                    
                    # Add to history
                    messages.append(LLMMessage(role="assistant", content=response.content))
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]")
                continue
    
    finally:
        if provider:
            await provider.close()
        console.print("\n[cyan]Goodbye![/cyan]")


@cli.command()
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("--model", default="whisper:base", help="STT model to use")
@click.pass_context
def transcribe(ctx, audio_file: str, model: str):
    """Transcribe an audio file."""
    console.print(f"[yellow]Transcription not yet implemented[/yellow]")
    console.print(f"File: {audio_file}")
    console.print(f"Model: {model}")


@cli.command()
@click.pass_context
def info(ctx):
    """Show system information."""
    env = ctx.obj["env"]
    config = ctx.obj.get("config")
    
    console.print(Panel.fit(
        "[bold]Skeleton App Information[/bold]",
        border_style="cyan"
    ))
    
    console.print("\n[bold]Environment:[/bold]")
    console.print(f"  Ollama Host: {env.ollama_host}")
    console.print(f"  OpenAI Key: {'Set' if env.openai_api_key else 'Not set'}")
    console.print(f"  Anthropic Key: {'Set' if env.anthropic_api_key else 'Not set'}")
    console.print(f"  Database: {env.database_url}")
    
    if config:
        console.print("\n[bold]Node Configuration:[/bold]")
        console.print(f"  ID: {config.node.id}")
        console.print(f"  Name: {config.node.name}")
        console.print(f"  Roles: {', '.join(config.node.roles)}")


def main():
    """Entry point for CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
