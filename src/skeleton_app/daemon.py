"""Main daemon entry point."""

import asyncio
import logging
import signal
from pathlib import Path

import click
from rich.console import Console

from skeleton_app.config import Config, EnvSettings

console = Console()
logger = logging.getLogger(__name__)


class SkeletonDaemon:
    """Main daemon process."""
    
    def __init__(self, config: Config, env: EnvSettings):
        self.config = config
        self.env = env
        self.running = False
    
    async def start(self):
        """Start the daemon."""
        self.running = True
        logger.info(f"Starting daemon: {self.config.node.name} ({self.config.node.id})")
        logger.info(f"Roles: {', '.join(self.config.node.roles)}")
        
        # TODO: Initialize subsystems
        # - Node registry
        # - Capability router
        # - LLM providers
        # - STT/TTS providers (if roles include them)
        # - Audio manager (if role includes audio_hub)
        # - Network API server
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Daemon cancelled")
    
    async def stop(self):
        """Stop the daemon."""
        logger.info("Stopping daemon...")
        self.running = False
        
        # TODO: Clean shutdown of subsystems


@click.command()
@click.option("--config", type=click.Path(exists=True), default="config.yaml", help="Path to config file")
@click.option("--log-level", default="INFO", help="Logging level")
def main(config: str, log_level: str):
    """Start the skeleton-app daemon."""
    
    # Set up logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Load configuration
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"[red]Error: Config file not found: {config}[/red]")
        console.print("[yellow]Hint: Copy config.example.yaml to config.yaml and edit it[/yellow]")
        return
    
    app_config = Config.from_yaml(config_path)
    env_settings = EnvSettings()
    
    # Create daemon
    daemon = SkeletonDaemon(app_config, env_settings)
    
    # Set up signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler(sig, frame):
        console.print("\n[yellow]Received shutdown signal[/yellow]")
        loop.create_task(daemon.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run daemon
    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
