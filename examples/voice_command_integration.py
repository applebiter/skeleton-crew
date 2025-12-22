"""
Example: Integrating voice commands into your application.

This shows how to connect to the voice command service and handle commands.
"""

import asyncio
import json
import logging
from typing import Callable, Dict

import websockets


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceCommandHandler:
    """
    Handler for voice commands - integrates with your application.
    
    Usage:
        handler = VoiceCommandHandler()
        
        # Register command handlers
        handler.register('transport_start', lambda: print("Starting transport"))
        handler.register('transport_stop', lambda: print("Stopping transport"))
        
        # Connect and listen
        await handler.connect('localhost', 8001)
    """
    
    def __init__(self):
        self.handlers: Dict[str, Callable] = {}
        self.websocket = None
        self.running = False
    
    def register(self, command: str, handler: Callable):
        """
        Register a command handler.
        
        Args:
            command: Command name (e.g., 'transport_start')
            handler: Function to call when command received
        """
        self.handlers[command] = handler
        logger.info(f"Registered handler for command: {command}")
    
    async def connect(self, host: str = 'localhost', port: int = 8001):
        """
        Connect to voice command service and start listening.
        
        Args:
            host: Service host
            port: Service port
        """
        ws_url = f"ws://{host}:{port}/ws"
        
        logger.info(f"Connecting to {ws_url}")
        
        try:
            async with websockets.connect(ws_url) as websocket:
                self.websocket = websocket
                self.running = True
                
                logger.info("✓ Connected to voice command service")
                
                # Keepalive task
                async def keepalive():
                    while self.running:
                        await asyncio.sleep(10)
                        try:
                            await websocket.send("ping")
                        except Exception:
                            break
                
                keepalive_task = asyncio.create_task(keepalive())
                
                try:
                    async for message in websocket:
                        await self._handle_message(message)
                finally:
                    self.running = False
                    keepalive_task.cancel()
        
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
        except KeyboardInterrupt:
            logger.info("Disconnected")
    
    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'connected':
                logger.info(f"Connected: {data.get('message')}")
                wake_words = data.get('wake_words', {})
                if wake_words:
                    logger.info(f"Wake words: {wake_words}")
            
            elif msg_type == 'transcription':
                if not data.get('partial'):
                    text = data.get('text', '')
                    confidence = data.get('confidence', 0.0)
                    logger.debug(f"Transcription: {text} ({confidence:.2f})")
            
            elif msg_type == 'wake_word':
                node_id = data.get('node_id', '')
                logger.info(f"🎤 Wake word detected for: {node_id}")
            
            elif msg_type == 'command':
                await self._handle_command(data)
        
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_command(self, data: Dict):
        """Handle a voice command."""
        command = data.get('command', '')
        target = data.get('target_node', '')
        raw_text = data.get('raw_text', '')
        confidence = data.get('confidence', 0.0)
        
        logger.info(f"⚡ Command: {command} (target: {target}, confidence: {confidence:.2f})")
        
        # Find and execute handler
        if command in self.handlers:
            try:
                handler = self.handlers[command]
                
                # Call handler (async or sync)
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
                
                logger.info(f"✓ Executed handler for: {command}")
            
            except Exception as e:
                logger.error(f"Error executing handler for {command}: {e}")
        else:
            logger.warning(f"No handler registered for command: {command}")


# Example usage with JACK transport control
class JACKTransportController:
    """Example: Control JACK transport with voice commands."""
    
    def __init__(self):
        self.handler = VoiceCommandHandler()
        
        # Register command handlers
        self.handler.register('transport_start', self.start_transport)
        self.handler.register('transport_stop', self.stop_transport)
        self.handler.register('transport_rewind', self.rewind_transport)
    
    def start_transport(self):
        """Start JACK transport."""
        logger.info("→ Starting JACK transport")
        # TODO: Actually control JACK
        # from skeleton_app.audio.jack_client import JackClientManager
        # jack_client.transport_start()
    
    def stop_transport(self):
        """Stop JACK transport."""
        logger.info("→ Stopping JACK transport")
        # TODO: Actually control JACK
        # jack_client.transport_stop()
    
    def rewind_transport(self):
        """Rewind JACK transport to start."""
        logger.info("→ Rewinding JACK transport")
        # TODO: Actually control JACK
        # jack_client.transport_locate(0)
    
    async def run(self):
        """Run the controller."""
        await self.handler.connect()


# Example usage with recording control
class RecordingController:
    """Example: Control recording with voice commands."""
    
    def __init__(self):
        self.handler = VoiceCommandHandler()
        self.recording = False
        
        # Register command handlers
        self.handler.register('recording_start', self.start_recording)
        self.handler.register('recording_stop', self.stop_recording)
        self.handler.register('recording_toggle', self.toggle_recording)
    
    def start_recording(self):
        """Start recording."""
        if not self.recording:
            logger.info("→ Starting recording")
            self.recording = True
            # TODO: Actually start recording
        else:
            logger.info("Already recording")
    
    def stop_recording(self):
        """Stop recording."""
        if self.recording:
            logger.info("→ Stopping recording")
            self.recording = False
            # TODO: Actually stop recording
        else:
            logger.info("Not recording")
    
    def toggle_recording(self):
        """Toggle recording on/off."""
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()
    
    async def run(self):
        """Run the controller."""
        await self.handler.connect()


# Example usage with custom application
async def main():
    """Main example."""
    
    # Create handler
    handler = VoiceCommandHandler()
    
    # Register some example handlers
    handler.register('transport_start', lambda: print("▶️  Play"))
    handler.register('transport_stop', lambda: print("⏸️  Stop"))
    handler.register('recording_start', lambda: print("🔴 Recording"))
    handler.register('save_project', lambda: print("💾 Saving..."))
    
    # You can also use async handlers
    async def async_handler():
        await asyncio.sleep(0.1)  # Simulate async work
        print("✨ Async command executed")
    
    handler.register('some_async_command', async_handler)
    
    # Connect and listen
    logger.info("Starting voice command handler")
    logger.info("Registered commands: " + ", ".join(handler.handlers.keys()))
    
    await handler.connect()


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
    
    # Or use one of the specialized controllers:
    # controller = JACKTransportController()
    # asyncio.run(controller.run())
    
    # controller = RecordingController()
    # asyncio.run(controller.run())
