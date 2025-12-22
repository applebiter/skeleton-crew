"""
JACK Transport Agent - receives OSC commands to coordinate JACK transport across the network.

This agent runs on each musician's machine and responds to coordinated start/stop/locate
commands sent by a TransportCoordinator. Uses OSC for robust, music-friendly messaging.
"""

import logging
import time
import threading
from typing import Optional, Callable

try:
    import jack
except ImportError:
    jack = None

try:
    from pythonosc import dispatcher, osc_server
    from pythonosc.udp_client import SimpleUDPClient
except ImportError:
    dispatcher = None
    osc_server = None
    SimpleUDPClient = None

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class TransportAgent(QObject):
    """
    JACK Transport Agent that listens for OSC commands.
    
    Responds to:
    - /transport/start <timestamp>: Start transport at specified time
    - /transport/stop <timestamp>: Stop transport at specified time
    - /transport/locate_start <frame> <timestamp>: Locate then start at specified time
    - /transport/locate <frame>: Locate immediately
    - /transport/query: Respond with current transport state
    
    Signals:
    - log: Emitted with log messages
    - error: Emitted with error messages
    - state_changed: Emitted when transport state changes
    """
    
    log = Signal(str)
    error = Signal(str)
    state_changed = Signal(dict)  # {state: str, frame: int, timestamp: float}
    
    def __init__(self,
                 jack_client_name: str = "transport_agent",
                 osc_host: str = "0.0.0.0",
                 osc_port: int = 5555,
                 coordinator_host: Optional[str] = None,
                 coordinator_port: int = 5556):
        """
        Initialize transport agent.
        
        Args:
            jack_client_name: Name for JACK client
            osc_host: Host to bind OSC server to (0.0.0.0 for all interfaces)
            osc_port: Port for OSC server
            coordinator_host: Optional host to send replies to
            coordinator_port: Port for coordinator replies
        """
        super().__init__()
        
        if jack is None:
            self.error.emit("JACK-Client not available. Install with: pip install JACK-Client")
            raise ImportError("JACK-Client not installed")
        
        if dispatcher is None:
            self.error.emit("python-osc not available. Install with: pip install python-osc")
            raise ImportError("python-osc not installed")
        
        self.jack_client_name = jack_client_name
        self.osc_host = osc_host
        self.osc_port = osc_port
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        
        # JACK client
        self.jack_client: Optional[jack.Client] = None
        
        # OSC server
        self.osc_dispatcher = dispatcher.Dispatcher()
        self.osc_server: Optional[osc_server.ThreadingOSCUDPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        
        # OSC client for replies
        self.osc_client: Optional[SimpleUDPClient] = None
        if coordinator_host:
            self.osc_client = SimpleUDPClient(coordinator_host, coordinator_port)
        
        # Setup OSC handlers
        self._setup_osc_handlers()
        
        # State tracking
        self.last_state = {"state": "unknown", "frame": 0, "timestamp": 0.0}
    
    def _setup_osc_handlers(self):
        """Setup OSC message handlers."""
        self.osc_dispatcher.map("/transport/start", self._handle_start)
        self.osc_dispatcher.map("/transport/stop", self._handle_stop)
        self.osc_dispatcher.map("/transport/locate_start", self._handle_locate_start)
        self.osc_dispatcher.map("/transport/locate", self._handle_locate)
        self.osc_dispatcher.map("/transport/query", self._handle_query)
        self.osc_dispatcher.set_default_handler(self._handle_unknown)
    
    def start(self):
        """Start the transport agent (JACK client and OSC server)."""
        try:
            # Connect to JACK
            self.jack_client = jack.Client(self.jack_client_name)
            self.log.emit(f"Connected to JACK as '{self.jack_client_name}'")
            
            # Start JACK client
            self.jack_client.activate()
            
            # Start OSC server
            self.osc_server = osc_server.ThreadingOSCUDPServer(
                (self.osc_host, self.osc_port),
                self.osc_dispatcher
            )
            self.server_thread = threading.Thread(
                target=self.osc_server.serve_forever,
                daemon=True
            )
            self.server_thread.start()
            self.log.emit(f"OSC server listening on {self.osc_host}:{self.osc_port}")
            
            # Start state monitoring
            self._start_state_monitor()
            
        except Exception as e:
            error_msg = f"Failed to start transport agent: {e}"
            logger.exception(error_msg)
            self.error.emit(error_msg)
            raise
    
    def stop(self):
        """Stop the transport agent."""
        if self.osc_server:
            self.osc_server.shutdown()
            self.osc_server = None
            self.log.emit("OSC server stopped")
        
        if self.jack_client:
            self.jack_client.deactivate()
            self.jack_client.close()
            self.jack_client = None
            self.log.emit("JACK client closed")
    
    def _start_state_monitor(self):
        """Start monitoring JACK transport state."""
        def monitor():
            while self.jack_client and self.osc_server:
                try:
                    state, position = self.jack_client.transport_query()
                    
                    # Handle state - it might be an int or an enum
                    if hasattr(state, 'name'):
                        state_str = str(state.name).lower()
                    else:
                        # Map integer state to string
                        state_map = {0: 'stopped', 1: 'rolling', 2: 'starting'}
                        state_str = state_map.get(int(state), 'unknown')
                    
                    current_state = {
                        "state": state_str,
                        "frame": position['frame'],
                        "timestamp": time.time()
                    }
                    
                    # Only emit if state changed
                    if (current_state["state"] != self.last_state["state"] or
                        abs(current_state["frame"] - self.last_state["frame"]) > 100):
                        self.state_changed.emit(current_state)
                        self.last_state = current_state
                    
                    time.sleep(0.1)  # Check 10 times per second
                except Exception as e:
                    logger.error(f"State monitor error: {e}")
                    time.sleep(1.0)
        
        threading.Thread(target=monitor, daemon=True).start()
    
    def _handle_start(self, address: str, *args):
        """Handle /transport/start <timestamp>"""
        if not args:
            self.log.emit("START (immediate)")
            threading.Thread(target=self._start_at, args=(time.time(),), daemon=True).start()
            return
        
        target_time = float(args[0])
        self.log.emit(f"START scheduled at {target_time} (in {target_time - time.time():.3f}s)")
        threading.Thread(target=self._start_at, args=(target_time,), daemon=True).start()
    
    def _handle_stop(self, address: str, *args):
        """Handle /transport/stop <timestamp>"""
        if not args:
            self.log.emit("STOP (immediate)")
            threading.Thread(target=self._stop_at, args=(time.time(),), daemon=True).start()
            return
        
        target_time = float(args[0])
        self.log.emit(f"STOP scheduled at {target_time} (in {target_time - time.time():.3f}s)")
        threading.Thread(target=self._stop_at, args=(target_time,), daemon=True).start()
    
    def _handle_locate_start(self, address: str, *args):
        """Handle /transport/locate_start <frame> <timestamp>"""
        if len(args) < 2:
            self.error.emit("locate_start requires <frame> <timestamp>")
            return
        
        frame = int(args[0])
        target_time = float(args[1])
        self.log.emit(f"LOCATE+START frame={frame} at {target_time} (in {target_time - time.time():.3f}s)")
        threading.Thread(target=self._locate_start_at, args=(frame, target_time), daemon=True).start()
    
    def _handle_locate(self, address: str, *args):
        """Handle /transport/locate <frame>"""
        if not args:
            self.error.emit("locate requires <frame>")
            return
        
        frame = int(args[0])
        self.log.emit(f"LOCATE frame={frame} (immediate)")
        if self.jack_client:
            self.jack_client.transport_locate(frame)
    
    def _handle_query(self, address: str, *args):
        """Handle /transport/query - send back current state."""
        if not self.jack_client:
            return
        
        try:
            state, position = self.jack_client.transport_query()
            
            # Handle state - it might be an int or an enum
            if hasattr(state, 'name'):
                state_str = str(state.name).lower()
            else:
                # Map integer state to string
                state_map = {0: 'stopped', 1: 'rolling', 2: 'starting'}
                state_str = state_map.get(int(state), 'unknown')
            
            # Send reply if we have a coordinator to reply to
            if self.osc_client:
                self.osc_client.send_message("/transport/state", [
                    state_str,
                    int(position['frame']),
                    float(time.time())
                ])
            
            self.log.emit(f"Query response: {state_str} @ frame {position['frame']}")
        except Exception as e:
            self.error.emit(f"Query failed: {e}")
    
    def _handle_unknown(self, address: str, *args):
        """Handle unknown OSC messages."""
        self.error.emit(f"Unknown OSC message: {address} {args}")
    
    def _start_at(self, target_time: float):
        """Start transport at specific time."""
        delay = target_time - time.time()
        if delay > 0:
            time.sleep(delay)
        
        if self.jack_client:
            actual_time = time.time()
            self.jack_client.transport_start()
            self.log.emit(f"Transport STARTED at {actual_time:.6f} (target: {target_time:.6f}, error: {(actual_time - target_time) * 1000:.2f}ms)")
    
    def _stop_at(self, target_time: float):
        """Stop transport at specific time."""
        delay = target_time - time.time()
        if delay > 0:
            time.sleep(delay)
        
        if self.jack_client:
            actual_time = time.time()
            self.jack_client.transport_stop()
            self.log.emit(f"Transport STOPPED at {actual_time:.6f} (target: {target_time:.6f}, error: {(actual_time - target_time) * 1000:.2f}ms)")
    
    def _locate_start_at(self, frame: int, target_time: float):
        """Locate to frame and start at specific time."""
        delay = target_time - time.time()
        if delay > 0:
            time.sleep(delay)
        
        if self.jack_client:
            actual_time = time.time()
            self.jack_client.transport_locate(frame)
            self.jack_client.transport_start()
            self.log.emit(f"Transport LOCATE+START frame={frame} at {actual_time:.6f} (target: {target_time:.6f}, error: {(actual_time - target_time) * 1000:.2f}ms)")
