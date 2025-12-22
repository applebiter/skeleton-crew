"""
Transport services - wrappers for integrating transport agent/coordinator with service discovery.
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, Signal

from skeleton_app.audio.transport_agent import TransportAgent
from skeleton_app.audio.transport_coordinator import TransportCoordinator, AgentInfo
from skeleton_app.service_discovery import ServiceInfo, ServiceType, ServiceStatus, HealthStatus

logger = logging.getLogger(__name__)


class TransportAgentService(QObject):
    """
    Service wrapper for TransportAgent.
    
    Integrates with service discovery and provides a consistent interface.
    """
    
    status_changed = Signal(ServiceStatus)
    health_changed = Signal(HealthStatus)
    log = Signal(str)
    error = Signal(str)
    
    def __init__(self,
                 node_id: str,
                 jack_client_name: str = "transport_agent",
                 osc_port: int = 5555,
                 coordinator_host: Optional[str] = None,
                 coordinator_port: int = 5556):
        """
        Initialize transport agent service.
        
        Args:
            node_id: ID of this node
            jack_client_name: Name for JACK client
            osc_port: Port for OSC server
            coordinator_host: Optional coordinator host for replies
            coordinator_port: Port for coordinator
        """
        super().__init__()
        
        self.node_id = node_id
        self.osc_port = osc_port
        self.agent: Optional[TransportAgent] = None
        self._status = ServiceStatus.UNAVAILABLE
        self._health = HealthStatus.UNKNOWN
        
        try:
            self.agent = TransportAgent(
                jack_client_name=jack_client_name,
                osc_host="0.0.0.0",
                osc_port=osc_port,
                coordinator_host=coordinator_host,
                coordinator_port=coordinator_port
            )
            
            # Connect signals
            self.agent.log.connect(self._on_log)
            self.agent.error.connect(self._on_error)
            self.agent.state_changed.connect(self._on_state_changed)
            
            self._health = HealthStatus.HEALTHY
            self.health_changed.emit(self._health)
            
        except Exception as e:
            logger.error(f"Failed to create transport agent: {e}")
            self._health = HealthStatus.UNHEALTHY
            self.health_changed.emit(self._health)
            raise
    
    def start(self):
        """Start the transport agent service."""
        if self.agent:
            try:
                self.agent.start()
                self._status = ServiceStatus.AVAILABLE
                self._health = HealthStatus.HEALTHY
                self.status_changed.emit(self._status)
                self.health_changed.emit(self._health)
                self.log.emit("Transport agent service started")
            except Exception as e:
                logger.error(f"Failed to start transport agent: {e}")
                self._status = ServiceStatus.UNAVAILABLE
                self._health = HealthStatus.UNHEALTHY
                self.status_changed.emit(self._status)
                self.health_changed.emit(self._health)
                raise
    
    def stop(self):
        """Stop the transport agent service."""
        if self.agent:
            self.agent.stop()
            self._status = ServiceStatus.UNAVAILABLE
            self.status_changed.emit(self._status)
            self.log.emit("Transport agent service stopped")
    
    def get_service_info(self) -> ServiceInfo:
        """Get service info for registration."""
        return ServiceInfo(
            node_id=self.node_id,
            service_type=ServiceType.JACK_TRANSPORT_AGENT,
            service_name=f"transport_agent_{self.node_id}",
            port=self.osc_port,
            protocol="osc",
            capabilities={
                "transport_control": True,
                "osc_commands": [
                    "/transport/start",
                    "/transport/stop",
                    "/transport/locate",
                    "/transport/locate_start",
                    "/transport/query"
                ]
            },
            metadata={
                "jack_client_name": self.agent.jack_client_name if self.agent else None,
                "osc_port": self.osc_port
            },
            status=self._status,
            health_status=self._health
        )
    
    @property
    def status(self) -> ServiceStatus:
        """Get current service status."""
        return self._status
    
    @property
    def health(self) -> HealthStatus:
        """Get current health status."""
        return self._health
    
    def _on_log(self, message: str):
        """Forward log message."""
        self.log.emit(message)
    
    def _on_error(self, message: str):
        """Handle error and update health."""
        self.error.emit(message)
        self._health = HealthStatus.DEGRADED
        self.health_changed.emit(self._health)
    
    def _on_state_changed(self, state: Dict):
        """Handle transport state change."""
        # Could update status based on transport state
        pass


class TransportCoordinatorService(QObject):
    """
    Service wrapper for TransportCoordinator.
    
    Integrates with service discovery and provides coordination interface.
    """
    
    status_changed = Signal(ServiceStatus)
    health_changed = Signal(HealthStatus)
    log = Signal(str)
    error = Signal(str)
    agent_state_changed = Signal(str, dict)
    
    def __init__(self,
                 node_id: str,
                 listen_port: int = 5556,
                 default_agent_port: int = 5555):
        """
        Initialize transport coordinator service.
        
        Args:
            node_id: ID of this node
            listen_port: Port to listen for agent replies
            default_agent_port: Default port for agents
        """
        super().__init__()
        
        self.node_id = node_id
        self.listen_port = listen_port
        self.coordinator: Optional[TransportCoordinator] = None
        self._status = ServiceStatus.UNAVAILABLE
        self._health = HealthStatus.UNKNOWN
        
        try:
            self.coordinator = TransportCoordinator(
                listen_port=listen_port,
                default_agent_port=default_agent_port
            )
            
            # Connect signals
            self.coordinator.log.connect(self._on_log)
            self.coordinator.error.connect(self._on_error)
            self.coordinator.agent_state_changed.connect(self._on_agent_state_changed)
            
            self._status = ServiceStatus.AVAILABLE
            self._health = HealthStatus.HEALTHY
            self.status_changed.emit(self._status)
            self.health_changed.emit(self._health)
            
        except Exception as e:
            logger.error(f"Failed to create transport coordinator: {e}")
            self._health = HealthStatus.UNHEALTHY
            self.health_changed.emit(self._health)
            raise
    
    def add_agent(self, host: str, port: Optional[int] = None, name: Optional[str] = None):
        """Add an agent to coordinate."""
        if self.coordinator:
            self.coordinator.add_agent(host, port, name)
    
    def add_agent_from_service_info(self, service_info: ServiceInfo):
        """Add an agent from a ServiceInfo object."""
        if service_info.service_type == ServiceType.JACK_TRANSPORT_AGENT:
            self.add_agent(
                host=service_info.endpoint or service_info.node_id,
                port=service_info.port,
                name=service_info.service_name
            )
    
    def remove_agent(self, host: str, port: Optional[int] = None):
        """Remove an agent."""
        if self.coordinator:
            self.coordinator.remove_agent(host, port)
    
    def clear_agents(self):
        """Remove all agents."""
        if self.coordinator:
            self.coordinator.clear_agents()
    
    def get_agents(self):
        """Get list of agents."""
        if self.coordinator:
            return self.coordinator.get_agents()
        return []
    
    def start_all(self, pre_roll_seconds: float = 3.0):
        """Start transport on all agents."""
        if self.coordinator:
            self.coordinator.start_all(pre_roll_seconds)
    
    def stop_all(self, pre_roll_seconds: float = 0.0):
        """Stop transport on all agents."""
        if self.coordinator:
            self.coordinator.stop_all(pre_roll_seconds)
    
    def locate_and_start_all(self, frame: int, pre_roll_seconds: float = 3.0):
        """Locate and start transport on all agents."""
        if self.coordinator:
            self.coordinator.locate_and_start_all(frame, pre_roll_seconds)
    
    def locate_all(self, frame: int):
        """Locate to frame on all agents."""
        if self.coordinator:
            self.coordinator.locate_all(frame)
    
    def query_all(self):
        """Query state from all agents."""
        if self.coordinator:
            self.coordinator.query_all()
    
    def get_service_info(self) -> ServiceInfo:
        """Get service info for registration."""
        return ServiceInfo(
            node_id=self.node_id,
            service_type=ServiceType.JACK_TRANSPORT_COORDINATOR,
            service_name=f"transport_coordinator_{self.node_id}",
            port=self.listen_port,
            protocol="osc",
            capabilities={
                "coordination": True,
                "commands": [
                    "start_all",
                    "stop_all",
                    "locate_all",
                    "locate_and_start_all",
                    "query_all"
                ]
            },
            metadata={
                "listen_port": self.listen_port,
                "agent_count": len(self.get_agents())
            },
            status=self._status,
            health_status=self._health
        )
    
    @property
    def status(self) -> ServiceStatus:
        """Get current service status."""
        return self._status
    
    @property
    def health(self) -> HealthStatus:
        """Get current health status."""
        return self._health
    
    def _on_log(self, message: str):
        """Forward log message."""
        self.log.emit(message)
    
    def _on_error(self, message: str):
        """Handle error and update health."""
        self.error.emit(message)
        self._health = HealthStatus.DEGRADED
        self.health_changed.emit(self._health)
    
    def _on_agent_state_changed(self, agent_host: str, state: Dict):
        """Forward agent state change."""
        self.agent_state_changed.emit(agent_host, state)
