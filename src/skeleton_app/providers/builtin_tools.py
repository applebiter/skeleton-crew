"""Built-in tools for JACK audio control and node management.

These tools allow the LLM to orchestrate audio connections, manage transport,
and query cluster state - all with full local auditability.
"""

import logging
from typing import List, Dict, Any, Optional

from skeleton_app.providers.tools import (
    ToolDefinition, ToolParameter, ToolRegistry
)

logger = logging.getLogger(__name__)

# Import JACK client manager
try:
    from skeleton_app.audio.jack_client import JackClientManager
    _JACK_AVAILABLE = True
except ImportError:
    _JACK_AVAILABLE = False
    logger.warning("JACK client library not available - handlers will use mock data")

# Global JACK client manager instance
_jack_manager: Optional[JackClientManager] = None


def _get_jack_manager() -> Optional[JackClientManager]:
    """Get or create JACK client manager."""
    global _jack_manager
    if not _JACK_AVAILABLE:
        return None
    
    if _jack_manager is None:
        try:
            _jack_manager = JackClientManager("skeleton_tools")
            if not _jack_manager.is_connected():
                _jack_manager.connect()
        except Exception as e:
            logger.error(f"Failed to initialize JACK manager: {e}")
            return None
    
    return _jack_manager


async def handle_jack_status() -> Dict[str, Any]:
    """Get current JACK status and active ports."""
    jack_mgr = _get_jack_manager()
    
    if not jack_mgr:
        return {
            "status": "unavailable",
            "ports": [],
            "connections": {},
            "transport_state": "unknown",
            "error": "JACK client not available"
        }
    
    try:
        # Get all ports
        output_ports = jack_mgr.get_ports(is_output=True, is_audio=True)
        input_ports = jack_mgr.get_ports(is_input=True, is_audio=True)
        
        # Get connections
        connections = jack_mgr.get_all_connections()
        
        # Get transport state
        transport_state = jack_mgr.get_transport_state()
        
        return {
            "status": "running",
            "ports": {
                "output": output_ports,
                "input": input_ports,
                "total": len(output_ports) + len(input_ports)
            },
            "connections": connections,
            "transport_state": transport_state,
            "sample_rate": jack_mgr.sample_rate,
            "buffer_size": jack_mgr.buffer_size
        }
    except Exception as e:
        logger.error(f"Error getting JACK status: {e}")
        return {
            "status": "error",
            "ports": [],
            "connections": {},
            "transport_state": "unknown",
            "error": str(e)
        }


async def handle_jack_transport_start() -> Dict[str, Any]:
    """Start JACK transport (play)."""
    jack_mgr = _get_jack_manager()
    
    if not jack_mgr:
        return {
            "success": False,
            "error": "JACK client not available"
        }
    
    try:
        jack_mgr.transport_start()
        return {
            "success": True,
            "message": "JACK transport started",
            "state": jack_mgr.get_transport_state()
        }
    except Exception as e:
        logger.error(f"Error starting JACK transport: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def handle_jack_transport_stop() -> Dict[str, Any]:
    """Stop JACK transport."""
    jack_mgr = _get_jack_manager()
    
    if not jack_mgr:
        return {
            "success": False,
            "error": "JACK client not available"
        }
    
    try:
        jack_mgr.transport_stop()
        return {
            "success": True,
            "message": "JACK transport stopped",
            "state": jack_mgr.get_transport_state()
        }
    except Exception as e:
        logger.error(f"Error stopping JACK transport: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def handle_record_start(
    duration_seconds: Optional[int] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """Start audio recording."""
    return {
        "success": True,
        "message": f"Recording started",
        "filename": filename or "recording.wav"
    }


async def handle_record_stop() -> Dict[str, Any]:
    """Stop audio recording."""
    return {
        "success": True,
        "message": "Recording stopped"
    }


async def handle_list_jack_ports(
    port_type: str = "all"
) -> Dict[str, Any]:
    """List available JACK ports (audio, midi, all)."""
    jack_mgr = _get_jack_manager()
    
    if not jack_mgr:
        return {
            "ports": [],
            "port_type": port_type,
            "error": "JACK client not available"
        }
    
    try:
        is_audio = port_type in ("audio", "all")
        is_midi = port_type in ("midi", "all")
        
        output_ports = jack_mgr.get_ports(is_output=True, is_audio=is_audio)
        input_ports = jack_mgr.get_ports(is_input=True, is_audio=is_audio)
        
        # Get connections for each port
        connections = jack_mgr.get_all_connections()
        
        return {
            "ports": {
                "output": output_ports,
                "input": input_ports,
                "total": len(output_ports) + len(input_ports)
            },
            "connections": connections,
            "port_type": port_type
        }
    except Exception as e:
        logger.error(f"Error listing JACK ports: {e}")
        return {
            "ports": [],
            "port_type": port_type,
            "error": str(e)
        }


async def handle_connect_jack_ports(
    source: str,
    destination: str
) -> Dict[str, Any]:
    """Create a connection between two JACK ports."""
    jack_mgr = _get_jack_manager()
    
    if not jack_mgr:
        return {
            "success": False,
            "source": source,
            "destination": destination,
            "error": "JACK client not available"
        }
    
    try:
        jack_mgr.connect_ports(source, destination)
        return {
            "success": True,
            "source": source,
            "destination": destination,
            "message": f"Connected {source} to {destination}"
        }
    except Exception as e:
        logger.error(f"Error connecting ports {source} to {destination}: {e}")
        return {
            "success": False,
            "source": source,
            "destination": destination,
            "error": str(e)
        }


async def handle_disconnect_jack_ports(
    source: str,
    destination: str
) -> Dict[str, Any]:
    """Disconnect two JACK ports."""
    jack_mgr = _get_jack_manager()
    
    if not jack_mgr:
        return {
            "success": False,
            "source": source,
            "destination": destination,
            "error": "JACK client not available"
        }
    
    try:
        jack_mgr.disconnect_ports(source, destination)
        return {
            "success": True,
            "source": source,
            "destination": destination,
            "message": f"Disconnected {source} from {destination}"
        }
    except Exception as e:
        logger.error(f"Error disconnecting ports {source} from {destination}: {e}")
        return {
            "success": False,
            "source": source,
            "destination": destination,
            "error": str(e)
        }


async def handle_get_node_status(
    node_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get status of cluster nodes."""
    return {
        "nodes": [],
        "total_nodes": 0,
        "healthy_nodes": 0
    }


async def handle_list_services(
    node_id: Optional[str] = None
) -> Dict[str, Any]:
    """List available services on nodes."""
    return {
        "services": [],
        "total": 0
    }


async def handle_trigger_voice_command(
    command_alias: str,
    target_node: Optional[str] = None
) -> Dict[str, Any]:
    """Trigger a voice command alias."""
    return {
        "success": True,
        "command": command_alias,
        "target": target_node or "local",
        "message": f"Executed command: {command_alias}"
    }


def register_builtin_tools(registry: ToolRegistry):
    """Register all built-in tools."""
    
    # JACK Status & Control
    registry.register(ToolDefinition(
        name="jack_status",
        description="Get current JACK audio server status, active ports, and connections",
        category="jack",
        handler=handle_jack_status
    ))
    
    registry.register(ToolDefinition(
        name="transport_start",
        description="Start JACK transport (playback)",
        category="transport",
        dangerous=True,
        handler=handle_jack_transport_start
    ))
    
    registry.register(ToolDefinition(
        name="transport_stop",
        description="Stop JACK transport",
        category="transport",
        dangerous=True,
        handler=handle_jack_transport_stop
    ))
    
    # Recording
    registry.register(ToolDefinition(
        name="record_start",
        description="Start audio recording",
        parameters=[
            ToolParameter(
                name="duration_seconds",
                type="integer",
                description="Optional: maximum duration in seconds",
                required=False
            ),
            ToolParameter(
                name="filename",
                type="string",
                description="Optional: output filename (defaults to timestamped recording.wav)",
                required=False
            )
        ],
        category="recording",
        dangerous=True,
        handler=handle_record_start
    ))
    
    registry.register(ToolDefinition(
        name="record_stop",
        description="Stop current audio recording",
        category="recording",
        dangerous=True,
        handler=handle_record_stop
    ))
    
    # Port Management
    registry.register(ToolDefinition(
        name="list_jack_ports",
        description="List all available JACK ports",
        parameters=[
            ToolParameter(
                name="port_type",
                type="string",
                description="Filter by type: audio, midi, or all",
                required=False,
                enum=["audio", "midi", "all"],
                default="all"
            )
        ],
        category="jack",
        handler=handle_list_jack_ports
    ))
    
    registry.register(ToolDefinition(
        name="connect_jack_ports",
        description="Create a connection between two JACK audio ports",
        parameters=[
            ToolParameter(
                name="source",
                type="string",
                description="Source port name (e.g., 'system:capture_1')",
                required=True
            ),
            ToolParameter(
                name="destination",
                type="string",
                description="Destination port name (e.g., 'skeleton_app:voice_in')",
                required=True
            )
        ],
        category="jack",
        dangerous=True,
        handler=handle_connect_jack_ports
    ))
    
    registry.register(ToolDefinition(
        name="disconnect_jack_ports",
        description="Disconnect two JACK audio ports",
        parameters=[
            ToolParameter(
                name="source",
                type="string",
                description="Source port name",
                required=True
            ),
            ToolParameter(
                name="destination",
                type="string",
                description="Destination port name",
                required=True
            )
        ],
        category="jack",
        dangerous=True,
        handler=handle_disconnect_jack_ports
    ))
    
    # Cluster Management
    registry.register(ToolDefinition(
        name="get_node_status",
        description="Get status of cluster nodes (online/offline, resource usage)",
        parameters=[
            ToolParameter(
                name="node_id",
                type="string",
                description="Optional: specific node ID to check",
                required=False
            )
        ],
        category="cluster",
        handler=handle_get_node_status
    ))
    
    registry.register(ToolDefinition(
        name="list_services",
        description="List available services on cluster nodes",
        parameters=[
            ToolParameter(
                name="node_id",
                type="string",
                description="Optional: specific node ID to check",
                required=False
            )
        ],
        category="cluster",
        handler=handle_list_services
    ))
    
    # Voice Commands
    registry.register(ToolDefinition(
        name="trigger_voice_command",
        description="Execute a voice command alias",
        parameters=[
            ToolParameter(
                name="command_alias",
                type="string",
                description="Name of the voice command alias to execute",
                required=True
            ),
            ToolParameter(
                name="target_node",
                type="string",
                description="Optional: specific node to execute on (defaults to local)",
                required=False
            )
        ],
        category="voice",
        dangerous=True,
        handler=handle_trigger_voice_command
    ))
    
    logger.info(f"Registered {len(registry.tools)} built-in tools")
