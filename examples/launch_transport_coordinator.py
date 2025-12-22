#!/usr/bin/env python3
"""
Example: Launch a transport coordinator (director machine).

Run this on the director/conductor machine to coordinate all agents.
"""

import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import QTimer

from skeleton_app.audio.transport_services import TransportCoordinatorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoordinatorWindow(QMainWindow):
    """Simple window for transport coordinator."""
    
    def __init__(self, node_id: str):
        super().__init__()
        self.setWindowTitle(f"Transport Coordinator - {node_id}")
        self.resize(400, 500)
        
        # Create service
        try:
            self.service = TransportCoordinatorService(
                node_id=node_id,
                listen_port=5556,
                default_agent_port=5555
            )
            
            # Import widget
            from skeleton_app.gui.widgets.transport_nodes import TransportCoordinatorNodeWidget
            
            # Create UI
            central = QWidget()
            layout = QVBoxLayout(central)
            
            self.node_widget = TransportCoordinatorNodeWidget(self.service)
            layout.addWidget(self.node_widget)
            
            self.setCentralWidget(central)
            
            # Add example agents from command line
            if len(sys.argv) > 2:
                for host in sys.argv[2:]:
                    self.service.add_agent(host.strip())
                    logger.info(f"Added agent: {host}")
                self.node_widget._update_agents_list()
            
        except Exception as e:
            logger.error(f"Failed to create coordinator: {e}")
            raise
    
    def closeEvent(self, event):
        """Clean shutdown."""
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Get node ID from command line or use hostname
    import socket
    node_id = sys.argv[1] if len(sys.argv) > 1 else socket.gethostname()
    
    window = CoordinatorWindow(node_id)
    window.show()
    
    logger.info("Transport coordinator ready")
    logger.info("Add agent hosts using the UI or pass them as command line arguments")
    logger.info("Example: python launch_transport_coordinator.py director 192.168.1.101 192.168.1.102")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
