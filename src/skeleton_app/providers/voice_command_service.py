"""
Voice command service with network API.

Provides a FastAPI-based service that exposes voice command functionality
over the LAN. Other nodes can subscribe to voice commands and receive
real-time transcription updates.
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from skeleton_app.audio.vosk_jack_stt import VoskJackSTT, TranscriptionResult, VoiceCommand
from skeleton_app.config import Config
from skeleton_app.service_discovery import ServiceDiscovery, ServiceInfo, ServiceType

logger = logging.getLogger(__name__)


@dataclass
class CommandAlias:
    """A command alias mapping."""
    alias: str
    actual_command: str
    node_id: Optional[str] = None  # None means global
    description: str = ""


class VoiceCommandService:
    """
    Voice command service with network API.
    
    Provides:
    - Real-time voice transcription via Vosk + JACK
    - Wake word detection for node-specific commands
    - WebSocket streaming of transcription results
    - REST API for command management
    - Command aliasing system
    - Multi-node discovery and registration
    """
    
    def __init__(self, config: Config, service_discovery: Optional[ServiceDiscovery] = None):
        """
        Initialize voice command service.
        
        Args:
            config: Application configuration
            service_discovery: Optional service discovery instance
        """
        self.config = config
        self.service_discovery = service_discovery
        
        # Vosk STT engine
        self.stt_engine: Optional[VoskJackSTT] = None
        
        # FastAPI app
        self.app = FastAPI(title="Voice Command Service")
        self._setup_routes()
        
        # WebSocket connections
        self.websocket_clients: Set[WebSocket] = set()
        
        # Command aliases
        self.aliases: Dict[str, CommandAlias] = {}
        self._load_default_aliases()
        
        # Command history
        self.command_history: List[Dict] = []
        self.max_history = 100
        
        # Stats
        self.stats = {
            'start_time': datetime.now(),
            'total_commands': 0,
            'total_transcriptions': 0,
            'active_connections': 0
        }
    
    def _load_default_aliases(self):
        """Load default command aliases."""
        # Transport commands
        self.add_alias("play", "transport_start", description="Start JACK transport")
        self.add_alias("stop", "transport_stop", description="Stop JACK transport")
        self.add_alias("record", "recording_start", description="Start recording")
        
        # Common actions
        self.add_alias("save", "save_project", description="Save current project")
        self.add_alias("load", "load_project", description="Load project")
        self.add_alias("new project", "create_project", description="Create new project")
        
        # Audio routing
        self.add_alias("connect", "jack_connect", description="Connect JACK ports")
        self.add_alias("disconnect", "jack_disconnect", description="Disconnect JACK ports")
        
        logger.info(f"Loaded {len(self.aliases)} default command aliases")
    
    def initialize_stt(self):
        """Initialize Vosk STT engine."""
        # Get model path from config
        vosk_config = self.config.stt.providers.get('realtime')
        if not vosk_config:
            raise ValueError("No realtime STT provider configured")
        
        model_path = vosk_config.model_path or f"./models/vosk/{vosk_config.model}"
        
        # Get wake words from config
        wake_words = {}
        if hasattr(self.config, 'voice_commands') and hasattr(self.config.voice_commands, 'wake_words'):
            wake_words = self.config.voice_commands.wake_words
        
        # Create STT engine
        logger.info(f"Initializing Vosk STT with model: {model_path}")
        self.stt_engine = VoskJackSTT(
            model_path=model_path,
            client_name=self.config.audio.jack.client_name + "_vosk",
            sample_rate=self.config.stt.vosk.get('sample_rate', 16000),
            wake_words=wake_words
        )
        
        # Register callbacks
        self.stt_engine.on_partial_result(self._on_partial_transcription)
        self.stt_engine.on_final_result(self._on_final_transcription)
        self.stt_engine.on_wake_word(self._on_wake_word)
        self.stt_engine.on_command(self._on_voice_command)
    
    def _on_partial_transcription(self, result: TranscriptionResult):
        """Handle partial transcription result."""
        asyncio.create_task(self._broadcast_transcription(result, partial=True))
    
    def _on_final_transcription(self, result: TranscriptionResult):
        """Handle final transcription result."""
        self.stats['total_transcriptions'] += 1
        asyncio.create_task(self._broadcast_transcription(result, partial=False))
    
    def _on_wake_word(self, node_id: str):
        """Handle wake word detection."""
        logger.info(f"Wake word detected for node: {node_id}")
        
        event = {
            'type': 'wake_word',
            'node_id': node_id,
            'timestamp': datetime.now().isoformat()
        }
        
        asyncio.create_task(self._broadcast_event(event))
    
    def _on_voice_command(self, command: VoiceCommand):
        """Handle voice command."""
        logger.info(
            f"Voice command: target={command.target_node}, "
            f"command={command.command}, confidence={command.confidence:.2f}"
        )
        
        self.stats['total_commands'] += 1
        
        # Apply aliasing
        processed_command = self._apply_alias(command)
        
        # Add to history
        self._add_to_history(processed_command)
        
        # Broadcast to connected clients
        event = {
            'type': 'command',
            'target_node': processed_command.target_node,
            'command': processed_command.command,
            'raw_text': processed_command.raw_text,
            'confidence': processed_command.confidence,
            'timestamp': datetime.now().isoformat()
        }
        
        asyncio.create_task(self._broadcast_event(event))
    
    def _apply_alias(self, command: VoiceCommand) -> VoiceCommand:
        """Apply command aliasing."""
        # Check for exact match
        if command.command in self.aliases:
            alias = self.aliases[command.command]
            
            # Check if alias is node-specific
            if alias.node_id and alias.node_id != command.target_node:
                return command
            
            logger.debug(f"Applied alias: '{command.command}' -> '{alias.actual_command}'")
            command.command = alias.actual_command
        
        return command
    
    def _add_to_history(self, command: VoiceCommand):
        """Add command to history."""
        self.command_history.append({
            'target_node': command.target_node,
            'command': command.command,
            'raw_text': command.raw_text,
            'confidence': command.confidence,
            'timestamp': datetime.now().isoformat()
        })
        
        # Trim history
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]
    
    async def _broadcast_transcription(self, result: TranscriptionResult, partial: bool):
        """Broadcast transcription to all WebSocket clients."""
        message = {
            'type': 'transcription',
            'text': result.text,
            'partial': partial,
            'confidence': result.confidence,
            'timestamp': datetime.now().isoformat()
        }
        
        await self._broadcast_event(message)
    
    async def _broadcast_event(self, event: Dict):
        """Broadcast event to all WebSocket clients."""
        disconnected = set()
        
        for client in self.websocket_clients:
            try:
                await client.send_json(event)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        self.websocket_clients -= disconnected
        self.stats['active_connections'] = len(self.websocket_clients)
    
    # API Routes
    
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.get("/")
        async def root():
            """Service info."""
            return {
                'service': 'voice_command',
                'version': '0.1.0',
                'status': 'running' if self.stt_engine and self.stt_engine.is_running() else 'stopped',
                'stats': self.stats
            }
        
        @self.app.get("/health")
        async def health():
            """Health check."""
            healthy = self.stt_engine and self.stt_engine.is_running()
            
            return {
                'healthy': healthy,
                'stt_engine': 'running' if healthy else 'stopped',
                'websocket_clients': len(self.websocket_clients)
            }
        
        @self.app.get("/stats")
        async def get_stats():
            """Get service statistics."""
            stats = self.stats.copy()
            
            if self.stt_engine:
                stats['stt_engine'] = self.stt_engine.get_stats()
            
            return stats
        
        @self.app.get("/wake-words")
        async def get_wake_words():
            """Get configured wake words."""
            if not self.stt_engine:
                raise HTTPException(status_code=503, detail="STT engine not initialized")
            
            return {'wake_words': self.stt_engine.wake_words}
        
        @self.app.post("/wake-words/{node_id}")
        async def add_wake_word(node_id: str, wake_word: str):
            """Add or update wake word for a node."""
            if not self.stt_engine:
                raise HTTPException(status_code=503, detail="STT engine not initialized")
            
            self.stt_engine.add_wake_word(node_id, wake_word)
            
            return {
                'status': 'success',
                'node_id': node_id,
                'wake_word': wake_word
            }
        
        @self.app.delete("/wake-words/{node_id}")
        async def remove_wake_word(node_id: str):
            """Remove wake word for a node."""
            if not self.stt_engine:
                raise HTTPException(status_code=503, detail="STT engine not initialized")
            
            self.stt_engine.remove_wake_word(node_id)
            
            return {
                'status': 'success',
                'node_id': node_id
            }
        
        @self.app.get("/aliases")
        async def get_aliases():
            """Get all command aliases."""
            return {
                'aliases': [asdict(alias) for alias in self.aliases.values()]
            }
        
        @self.app.post("/aliases")
        async def add_alias_route(
            alias: str,
            actual_command: str,
            node_id: Optional[str] = None,
            description: str = ""
        ):
            """Add a command alias."""
            self.add_alias(alias, actual_command, node_id, description)
            
            return {
                'status': 'success',
                'alias': alias,
                'actual_command': actual_command
            }
        
        @self.app.delete("/aliases/{alias}")
        async def remove_alias_route(alias: str):
            """Remove a command alias."""
            if alias in self.aliases:
                del self.aliases[alias]
                return {'status': 'success', 'alias': alias}
            else:
                raise HTTPException(status_code=404, detail="Alias not found")
        
        @self.app.get("/history")
        async def get_history(limit: int = 50):
            """Get command history."""
            return {
                'history': self.command_history[-limit:]
            }
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time transcription streaming."""
            await websocket.accept()
            self.websocket_clients.add(websocket)
            self.stats['active_connections'] = len(self.websocket_clients)
            
            logger.info(f"WebSocket client connected. Total: {len(self.websocket_clients)}")
            
            try:
                # Send initial status
                await websocket.send_json({
                    'type': 'connected',
                    'message': 'Connected to voice command service',
                    'wake_words': self.stt_engine.wake_words if self.stt_engine else {}
                })
                
                # Keep connection alive
                while True:
                    # Wait for client messages (e.g., pings)
                    data = await websocket.receive_text()
                    
                    # Echo back for keepalive
                    if data == 'ping':
                        await websocket.send_json({'type': 'pong'})
            
            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self.websocket_clients.discard(websocket)
                self.stats['active_connections'] = len(self.websocket_clients)
    
    # Public API
    
    def add_alias(
        self,
        alias: str,
        actual_command: str,
        node_id: Optional[str] = None,
        description: str = ""
    ):
        """Add a command alias."""
        self.aliases[alias] = CommandAlias(
            alias=alias,
            actual_command=actual_command,
            node_id=node_id,
            description=description
        )
        
        logger.debug(f"Added alias: '{alias}' -> '{actual_command}'")
    
    async def start(self):
        """Start the voice command service."""
        logger.info("Starting voice command service")
        
        # Initialize STT engine
        self.initialize_stt()
        
        # Start STT engine
        self.stt_engine.start()
        
        # Register with service discovery
        if self.service_discovery:
            await self._register_service()
        
        logger.info("Voice command service started")
    
    async def stop(self):
        """Stop the voice command service."""
        logger.info("Stopping voice command service")
        
        # Stop STT engine
        if self.stt_engine:
            self.stt_engine.stop()
        
        # Close WebSocket connections
        for client in list(self.websocket_clients):
            try:
                await client.close()
            except Exception:
                pass
        
        self.websocket_clients.clear()
        
        logger.info("Voice command service stopped")
    
    async def _register_service(self):
        """Register service with service discovery."""
        if not self.service_discovery:
            return
        
        service_info = ServiceInfo(
            node_id=self.config.node.id,
            service_type=ServiceType.STT_ENGINE,
            service_name="voice_command",
            endpoint=f"http://{self.config.node.host}:{self.config.node.port}",
            port=self.config.node.port,
            protocol="http",
            capabilities={
                'stt_engine': 'vosk',
                'jack_aware': True,
                'real_time': True,
                'wake_words': True,
                'command_aliasing': True,
                'websocket_streaming': True
            },
            metadata={
                'model': self.config.stt.providers['realtime'].model,
                'sample_rate': self.config.stt.vosk.get('sample_rate', 16000),
                'jack_client': self.stt_engine.client_name if self.stt_engine else None
            }
        )
        
        await self.service_discovery.register_service(service_info)
        logger.info("Registered voice command service with discovery")
    
    def run(self, host: str = "0.0.0.0", port: int = 8001):
        """
        Run the service (blocking).
        
        Args:
            host: Host to bind to
            port: Port to bind to
        """
        # Start STT in background
        asyncio.create_task(self.start())
        
        # Run FastAPI server
        uvicorn.run(
            self.app,
            host=host,
            port=port,
            log_level="info"
        )


# Standalone entry point
async def main():
    """Main entry point for standalone service."""
    from skeleton_app.config import load_config
    
    config = load_config()
    
    service = VoiceCommandService(config)
    
    try:
        await service.start()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await service.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
