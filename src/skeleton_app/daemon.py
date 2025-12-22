"""Main daemon entry point."""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from skeleton_app.config import Config, EnvSettings
from skeleton_app.database import Database
from skeleton_app.service_discovery import ServiceDiscovery, ServiceInfo, ServiceType, ServiceStatus

console = Console()
logger = logging.getLogger(__name__)


class SkeletonDaemon:
    """Main daemon process."""
    
    def __init__(self, config: Config, env: EnvSettings):
        self.config = config
        self.env = env
        self.running = False
        self.database: Optional[Database] = None
        self.service_discovery: Optional[ServiceDiscovery] = None
    
    async def start(self):
        """Start the daemon."""
        self.running = True
        logger.info(f"Starting daemon: {self.config.node.name} ({self.config.node.id})")
        logger.info(f"Roles: {', '.join(self.config.node.roles)}")
        
        # Initialize database connection
        if self.config.database:
            self.database = Database(self.config.database.url)
            await self.database.connect()
            await self.database.initialize_schema()
            logger.info("Database connected")
        
        # Initialize service discovery
        self.service_discovery = ServiceDiscovery(
            node_id=self.config.node.id,
            node_name=self.config.node.name,
            node_host=self.config.node.host,
            database=self.database,
            heartbeat_interval=10,
            discovery_bridge=None  # No Qt bridge in daemon
        )
        await self.service_discovery.start()
        
        # Register node in database
        await self._register_node()
        
        # Advertise services based on roles
        await self._advertise_services()
        
        logger.info("Daemon started successfully")
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Daemon cancelled")
    
    async def stop(self):
        """Stop the daemon."""
        logger.info("Stopping daemon...")
        self.running = False
        
        # Stop service discovery
        if self.service_discovery:
            await self.service_discovery.stop()
        
        # Disconnect database
        if self.database:
            await self.database.disconnect()
        
        logger.info("Daemon stopped")
    
    async def _register_node(self):
        """Register this node in the database."""
        if not self.database or not self.database.pool:
            return
        
        async with self.database.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO nodes (id, name, host, port, roles, capabilities, tags, status, last_seen)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    host = EXCLUDED.host,
                    port = EXCLUDED.port,
                    roles = EXCLUDED.roles,
                    capabilities = EXCLUDED.capabilities,
                    tags = EXCLUDED.tags,
                    status = EXCLUDED.status,
                    last_seen = NOW(),
                    updated_at = NOW()
            """, 
                self.config.node.id,
                self.config.node.name,
                self.config.node.host,
                self.config.node.port,
                self.config.node.roles,
                [],  # capabilities - will be populated from services
                self.config.node.tags,
                "online"
            )
        
        logger.info(f"Node registered: {self.config.node.name}")
    
    async def _advertise_services(self):
        """Advertise available services based on node roles and configuration."""
        if not self.service_discovery:
            return
        
        # LLM Inference service (if Ollama configured)
        if "llm_inference" in self.config.node.roles and self.config.providers.ollama.enabled:
            service = ServiceInfo(
                node_id=self.config.node.id,
                service_type=ServiceType.LLM_INFERENCE,
                service_name=f"ollama_{self.config.node.name}",
                endpoint=self.config.providers.ollama.base_url,
                port=11434,
                protocol="http",
                capabilities={
                    "models": self.config.providers.ollama.available_models,
                    "embedding": True,
                    "tool_calling": True
                },
                metadata={
                    "provider": "ollama",
                    "default_model": self.config.providers.ollama.default_model
                }
            )
            await self.service_discovery.register_service(service)
            logger.info(f"Advertised LLM service: {service.service_name}")
        
        # TODO: Add more service types:
        # - JACK audio (detect JACK server and ports)
        # - STT engine (if whisper/vosk available)
        # - TTS engine (if piper available)
        # - MIDI routing (if QmidiNet running)
        # - OSC server (if enabled)
        # - Media library (if configured)


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
