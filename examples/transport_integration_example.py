"""
Example: Integrate transport coordination into your main skeleton-app.

This shows how to add transport agent/coordinator nodes to your existing
node canvas and service registry.
"""

import asyncio
import logging
from typing import Dict

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import QTimer

from skeleton_app.audio.transport_services import (
    TransportAgentService,
    TransportCoordinatorService
)
from skeleton_app.gui.widgets.transport_nodes import (
    TransportAgentNodeWidget,
    TransportCoordinatorNodeWidget
)
from skeleton_app.service_discovery import ServiceDiscovery, ServiceType
from skeleton_app.database import Database

logger = logging.getLogger(__name__)


class TransportIntegratedApp:
    """
    Example app showing transport coordination integrated with
    service discovery and node canvas.
    """
    
    def __init__(self, node_id: str, role: str = "musician"):
        """
        Initialize app.
        
        Args:
            node_id: Unique ID for this node
            role: Either "musician" or "director"
        """
        self.node_id = node_id
        self.role = role
        
        # Service discovery (would be initialized in main app)
        self.discovery: ServiceDiscovery = None
        
        # Transport services
        self.transport_agent: TransportAgentService = None
        self.transport_coordinator: TransportCoordinatorService = None
        
        # Widgets for node canvas
        self.transport_widgets: Dict[str, QWidget] = {}
    
    async def initialize_services(self):
        """Initialize transport services based on role."""
        
        if self.role == "musician" or self.role == "both":
            # Create transport agent
            self.transport_agent = TransportAgentService(
                node_id=self.node_id,
                jack_client_name=f"transport_{self.node_id}",
                osc_port=5555
            )
            
            # Start agent
            self.transport_agent.start()
            
            # Register with service discovery
            if self.discovery:
                service_info = self.transport_agent.get_service_info()
                await self.discovery.register_service(service_info)
            
            logger.info(f"Transport agent initialized for {self.node_id}")
        
        if self.role == "director" or self.role == "both":
            # Create transport coordinator
            self.transport_coordinator = TransportCoordinatorService(
                node_id=self.node_id,
                listen_port=5556
            )
            
            # Register with service discovery
            if self.discovery:
                service_info = self.transport_coordinator.get_service_info()
                await self.discovery.register_service(service_info)
            
            # Auto-discover agents
            await self.discover_agents()
            
            logger.info(f"Transport coordinator initialized for {self.node_id}")
    
    async def discover_agents(self):
        """Auto-discover transport agents on the network."""
        if not self.discovery or not self.transport_coordinator:
            return
        
        # Find all available transport agents
        agents = await self.discovery.find_services(
            service_type=ServiceType.JACK_TRANSPORT_AGENT,
            status="available"
        )
        
        # Add each agent to coordinator
        for agent_info in agents:
            self.transport_coordinator.add_agent_from_service_info(agent_info)
            logger.info(f"Auto-discovered agent: {agent_info.node_id}")
    
    def create_canvas_widgets(self) -> Dict[str, QWidget]:
        """
        Create widgets for node canvas representation.
        
        Returns:
            Dictionary of widget_id -> widget
        """
        widgets = {}
        
        if self.transport_agent:
            agent_widget = TransportAgentNodeWidget(self.transport_agent)
            widgets[f"transport_agent_{self.node_id}"] = agent_widget
        
        if self.transport_coordinator:
            coord_widget = TransportCoordinatorNodeWidget(self.transport_coordinator)
            widgets[f"transport_coordinator_{self.node_id}"] = coord_widget
        
        self.transport_widgets = widgets
        return widgets
    
    def get_node_metadata_for_canvas(self):
        """
        Get metadata for adding these as nodes to your canvas.
        
        Returns data in the format your node canvas expects.
        """
        nodes = []
        
        if self.transport_agent:
            nodes.append({
                "id": f"transport_agent_{self.node_id}",
                "type": "transport_agent",
                "name": f"Transport Agent ({self.node_id})",
                "widget": self.transport_widgets.get(f"transport_agent_{self.node_id}"),
                "inputs": [],  # Transport agents don't have input pins
                "outputs": [
                    {"name": "state_changed", "type": "signal"},
                ],
                "color": self.transport_widgets[f"transport_agent_{self.node_id}"].get_node_color(),
            })
        
        if self.transport_coordinator:
            nodes.append({
                "id": f"transport_coordinator_{self.node_id}",
                "type": "transport_coordinator",
                "name": f"Coordinator ({self.node_id})",
                "widget": self.transport_widgets.get(f"transport_coordinator_{self.node_id}"),
                "inputs": [
                    {"name": "start", "type": "action"},
                    {"name": "stop", "type": "action"},
                    {"name": "locate", "type": "action"},
                ],
                "outputs": [
                    {"name": "command_sent", "type": "signal"},
                ],
                "color": self.transport_widgets[f"transport_coordinator_{self.node_id}"].get_node_color(),
            })
        
        return nodes
    
    async def shutdown(self):
        """Clean shutdown."""
        if self.transport_agent:
            self.transport_agent.stop()
        
        # Coordinator doesn't need explicit stop
        
        if self.discovery:
            # Unregister services
            pass  # Would call discovery.unregister_service()
        
        logger.info("Transport services shut down")


# Example usage in main app
async def example_main():
    """Example of how to use in your main app."""
    import sys
    
    # Initialize Qt application
    app = QApplication(sys.argv)
    
    # Determine role (would come from config or command line)
    import socket
    node_id = socket.gethostname()
    role = sys.argv[1] if len(sys.argv) > 1 else "musician"
    
    # Create integrated app
    transport_app = TransportIntegratedApp(node_id, role)
    
    # Initialize services
    await transport_app.initialize_services()
    
    # Create canvas widgets
    widgets = transport_app.create_canvas_widgets()
    
    # In your main window, you would add these to your node canvas:
    # for node_data in transport_app.get_node_metadata_for_canvas():
    #     canvas.add_node(node_data)
    
    # For this example, just show the widgets standalone
    main_window = QMainWindow()
    main_window.setWindowTitle(f"Transport Integration - {node_id} ({role})")
    
    central = QWidget()
    layout = QVBoxLayout(central)
    
    for widget in widgets.values():
        layout.addWidget(widget)
    
    main_window.setCentralWidget(central)
    main_window.show()
    
    # Run app
    sys.exit(app.exec())


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    # Run with async
    asyncio.run(example_main())
