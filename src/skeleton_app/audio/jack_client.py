"""
JACK client manager for skeleton-app.

Provides high-level interface to JACK audio server with transport control.
"""

import logging
from typing import Optional, List, Tuple, Dict
from enum import Enum

import jack

logger = logging.getLogger(__name__)


class TransportState(Enum):
    """JACK transport states."""
    STOPPED = "Stopped"
    ROLLING = "Rolling"
    STARTING = "Starting"


class JackClientManager:
    """
    Manages JACK client connection and provides transport control.
    
    This wraps the jack-client library and provides a clean interface
    for the GUI and other components.
    """
    
    def __init__(self, client_name: str = "skeleton_crew"):
        """
        Initialize JACK client manager.
        
        Args:
            client_name: Name for the JACK client
        """
        self.client_name = client_name
        self.client: Optional[jack.Client] = None
        self._connected = False
        self.monitor_ports = []  # Store created ports
    
    def connect(self):
        """
        Connect to JACK server.
        
        Raises:
            RuntimeError: If connection fails
        """
        try:
            self.client = jack.Client(self.client_name)
            
            # Create monitor ports so we appear in the graph
            # Input ports (we can receive audio for monitoring/recording)
            self.monitor_ports.append(
                self.client.inports.register('monitor_in_L')
            )
            self.monitor_ports.append(
                self.client.inports.register('monitor_in_R')
            )
            
            # Output ports (we can send audio out)
            self.monitor_ports.append(
                self.client.outports.register('monitor_out_L')
            )
            self.monitor_ports.append(
                self.client.outports.register('monitor_out_R')
            )
            
            self.client.activate()  # Must activate to appear in JACK graph
            self._connected = True
            logger.info(f"Connected to JACK as '{self.client_name}'")
            logger.info(f"Sample rate: {self.client.samplerate} Hz")
            logger.info(f"Buffer size: {self.client.blocksize} frames")
        except jack.JackError as e:
            logger.error(f"Failed to connect to JACK: {e}")
            raise RuntimeError(f"JACK connection failed: {e}") from e
    
    def disconnect(self):
        """Disconnect from JACK server."""
        if self.client:
            try:
                self.client.deactivate()
                self.client.close()
            except Exception as e:
                logger.warning(f"Error during JACK disconnect: {e}")
            finally:
                self.client = None
                self._connected = False
                logger.info("Disconnected from JACK")
    
    def is_connected(self) -> bool:
        """Check if connected to JACK server."""
        return self._connected and self.client is not None
    
    # Transport Control
    
    def get_transport_state(self) -> str:
        """
        Get current transport state.
        
        Returns:
            Transport state as string
        """
        if not self.client:
            return "N/A"
        
        state = self.client.transport_state
        if state == jack.STOPPED:
            return TransportState.STOPPED.value
        elif state == jack.ROLLING:
            return TransportState.ROLLING.value
        elif state == jack.STARTING:
            return TransportState.STARTING.value
        else:
            return "Unknown"
    
    def transport_start(self):
        """Start JACK transport."""
        if self.client:
            self.client.transport_start()
            logger.debug("Transport started")
    
    def transport_stop(self):
        """Stop JACK transport."""
        if self.client:
            self.client.transport_stop()
            logger.debug("Transport stopped")
    
    def transport_locate(self, frame: int):
        """
        Locate to specific frame.
        
        Args:
            frame: Frame number to locate to
        """
        if self.client:
            self.client.transport_locate(frame)
            logger.debug(f"Transport located to frame {frame}")
    
    def get_transport_frame(self) -> int:
        """
        Get current transport frame position.
        
        Returns:
            Current frame number
        """
        if self.client:
            return self.client.transport_frame
        return 0
    
    def get_transport_time(self) -> Tuple[int, int, int, int]:
        """
        Get transport time in hours, minutes, seconds, frames.
        
        Returns:
            Tuple of (hours, minutes, seconds, frames)
        """
        if not self.client:
            return (0, 0, 0, 0)
        
        frame = self.client.transport_frame
        fps = self.client.samplerate / self.client.blocksize
        
        total_seconds = frame / self.client.samplerate
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        frames = int((total_seconds % 1) * fps)
        
        return (hours, minutes, seconds, frames)
    
    # Port Management
    
    def get_ports(self, name_pattern: str = "", 
                  is_audio: bool = None,
                  is_input: bool = False,
                  is_output: bool = False) -> List[str]:
        """
        Get list of JACK ports matching criteria.
        
        Args:
            name_pattern: Port name pattern (regex)
            is_audio: Filter audio ports (None = all types, True = audio only, False = MIDI only)
            is_input: Filter input ports
            is_output: Filter output ports
        
        Returns:
            List of port names
        """
        if not self.client:
            return []
        
        # Build kwargs - only include is_audio if specified
        kwargs = {
            'name_pattern': name_pattern,
            'is_input': is_input,
            'is_output': is_output
        }
        if is_audio is not None:
            kwargs['is_audio'] = is_audio
        
        # Use the correct JACK-Client API
        ports = self.client.get_ports(**kwargs)
        
        return [p.name for p in ports]
    
    def get_all_connections(self) -> Dict[str, List[str]]:
        """
        Get all port connections in JACK graph.
        
        Returns:
            Dictionary mapping output ports to list of connected input ports
        """
        if not self.client:
            return {}
        
        connections = {}
        # Get all output ports (audio + MIDI)
        output_ports = self.get_ports(is_output=True)
        
        for port_name in output_ports:
            try:
                port = self.client.get_port_by_name(port_name)
                connected = self.client.get_all_connections(port)
                if connected:
                    connections[port_name] = [p.name for p in connected]
            except Exception as e:
                logger.warning(f"Error getting connections for {port_name}: {e}")
        
        return connections
    
    def connect_ports(self, output_port: str, input_port: str):
        """
        Connect two JACK ports.
        
        Args:
            output_port: Output port name
            input_port: Input port name
        """
        if not self.client:
            return
        
        try:
            self.client.connect(output_port, input_port)
            logger.info(f"Connected {output_port} → {input_port}")
        except jack.JackError as e:
            logger.error(f"Failed to connect ports: {e}")
            raise
    
    def disconnect_ports(self, output_port: str, input_port: str):
        """
        Disconnect two JACK ports.
        
        Args:
            output_port: Output port name
            input_port: Input port name
        """
        if not self.client:
            return
        
        try:
            self.client.disconnect(output_port, input_port)
            logger.info(f"Disconnected {output_port} ⛔ {input_port}")
        except jack.JackError as e:
            logger.error(f"Failed to disconnect ports: {e}")
            raise
    
    # Server Info
    
    @property
    def sample_rate(self) -> int:
        """Get JACK server sample rate."""
        return self.client.samplerate if self.client else 0
    
    @property
    def buffer_size(self) -> int:
        """Get JACK server buffer size."""
        return self.client.blocksize if self.client else 0
    
    @property
    def xruns(self) -> int:
        """Get xrun count (if available)."""
        # Note: JACK-Client doesn't directly expose xruns, would need to track via callback
        return 0
