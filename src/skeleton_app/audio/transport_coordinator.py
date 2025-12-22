"""
JACK Transport Coordinator - sends coordinated OSC commands to multiple transport agents.

This coordinator runs on the "director" machine and orchestrates synchronized
transport start/stop/locate across all musician machines.
"""

import logging
import time
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field

try:
    from pythonosc import dispatcher, osc_server
    from pythonosc.udp_client import SimpleUDPClient
except ImportError:
    dispatcher = None
    osc_server = None
    SimpleUDPClient = None

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Information about a remote transport agent."""
    host: str
    port: int = 5555
    name: Optional[str] = None
    last_state: Dict = field(default_factory=dict)
    online: bool = False


class TransportCoordinator(QObject):
    """
    Coordinates JACK transport across multiple machines via OSC.
    
    Sends synchronized commands to all registered agents.
    Optionally monitors agent states.
    
    Signals:
    - log: Emitted with log messages
    - error: Emitted with error messages
    - agent_state_changed: Emitted when agent state updates
    """
    
    log = Signal(str)
    error = Signal(str)
    agent_state_changed = Signal(str, dict)  # (agent_host, state_dict)
    
    def __init__(self,
                 listen_port: int = 5556,
                 default_agent_port: int = 5555):
        """
        Initialize transport coordinator.
        
        Args:
            listen_port: Port to listen for agent replies
            default_agent_port: Default port for agents
        """
        super().__init__()
        
        if dispatcher is None:
            self.error.emit("python-osc not available. Install with: pip install python-osc")
            raise ImportError("python-osc not installed")
        
        self.listen_port = listen_port
        self.default_agent_port = default_agent_port
        
        # Registered agents
        self.agents: Dict[str, AgentInfo] = {}
        
        # OSC clients (one per agent)
        self.osc_clients: Dict[str, SimpleUDPClient] = {}
        
        # OSC server for receiving replies
        self.osc_dispatcher = dispatcher.Dispatcher()
        self.osc_server: Optional[osc_server.ThreadingOSCUDPServer] = None
        
        # Setup OSC handlers for replies
        self._setup_osc_handlers()
    
    def _setup_osc_handlers(self):
        """Setup OSC message handlers for agent replies."""
        self.osc_dispatcher.map("/transport/state", self._handle_agent_state)
    
    def add_agent(self, host: str, port: Optional[int] = None, name: Optional[str] = None):
        """
        Add a transport agent to coordinate.
        
        Args:
            host: Agent hostname or IP
            port: Agent OSC port (defaults to default_agent_port)
            name: Optional friendly name
        """
        port = port or self.default_agent_port
        agent_id = f"{host}:{port}"
        
        if agent_id in self.agents:
            self.log.emit(f"Agent {agent_id} already registered")
            return
        
        self.agents[agent_id] = AgentInfo(
            host=host,
            port=port,
            name=name or host
        )
        
        # Create OSC client for this agent
        self.osc_clients[agent_id] = SimpleUDPClient(host, port)
        
        self.log.emit(f"Added agent: {agent_id} ({name or host})")
    
    def remove_agent(self, host: str, port: Optional[int] = None):
        """Remove an agent."""
        port = port or self.default_agent_port
        agent_id = f"{host}:{port}"
        
        if agent_id in self.agents:
            del self.agents[agent_id]
            del self.osc_clients[agent_id]
            self.log.emit(f"Removed agent: {agent_id}")
    
    def clear_agents(self):
        """Remove all agents."""
        self.agents.clear()
        self.osc_clients.clear()
        self.log.emit("Cleared all agents")
    
    def get_agents(self) -> List[AgentInfo]:
        """Get list of registered agents."""
        return list(self.agents.values())
    
    def start_all(self, pre_roll_seconds: float = 3.0):
        """
        Start transport on all agents.
        
        Args:
            pre_roll_seconds: Seconds from now to start
        """
        target_time = time.time() + pre_roll_seconds
        self._send_to_all("/transport/start", [target_time])
        self.log.emit(f"Sent START to all agents (target: {target_time:.6f}, in {pre_roll_seconds}s)")
    
    def stop_all(self, pre_roll_seconds: float = 0.0):
        """
        Stop transport on all agents.
        
        Args:
            pre_roll_seconds: Seconds from now to stop (0 = immediate)
        """
        if pre_roll_seconds > 0:
            target_time = time.time() + pre_roll_seconds
            self._send_to_all("/transport/stop", [target_time])
            self.log.emit(f"Sent STOP to all agents (target: {target_time:.6f}, in {pre_roll_seconds}s)")
        else:
            self._send_to_all("/transport/stop", [])
            self.log.emit("Sent STOP to all agents (immediate)")
    
    def locate_and_start_all(self, frame: int, pre_roll_seconds: float = 3.0):
        """
        Locate to frame and start transport on all agents.
        
        Args:
            frame: Frame to locate to
            pre_roll_seconds: Seconds from now to start
        """
        target_time = time.time() + pre_roll_seconds
        self._send_to_all("/transport/locate_start", [frame, target_time])
        self.log.emit(f"Sent LOCATE+START frame={frame} to all agents (target: {target_time:.6f}, in {pre_roll_seconds}s)")
    
    def locate_all(self, frame: int):
        """
        Locate to frame on all agents (immediate).
        
        Args:
            frame: Frame to locate to
        """
        self._send_to_all("/transport/locate", [frame])
        self.log.emit(f"Sent LOCATE frame={frame} to all agents")
    
    def query_all(self):
        """Query current state from all agents."""
        self._send_to_all("/transport/query", [])
        self.log.emit("Sent QUERY to all agents")
    
    def _send_to_all(self, address: str, args: List):
        """Send OSC message to all registered agents."""
        for agent_id, client in self.osc_clients.items():
            try:
                client.send_message(address, args)
            except Exception as e:
                self.error.emit(f"Failed to send to {agent_id}: {e}")
    
    def _handle_agent_state(self, address: str, *args):
        """Handle /transport/state reply from an agent."""
        # Try to identify which agent sent this
        # (This is a limitation of UDP OSC - we don't know the sender)
        # For now, just log it
        if len(args) >= 3:
            state = str(args[0])
            frame = int(args[1])
            timestamp = float(args[2])
            
            state_dict = {
                "state": state,
                "frame": frame,
                "timestamp": timestamp
            }
            
            # Update all agents (since we can't identify sender)
            # In practice, you'd need a better identification mechanism
            for agent_id, agent in self.agents.items():
                agent.last_state = state_dict
                agent.online = True
            
            self.log.emit(f"Agent state: {state} @ frame {frame}")
