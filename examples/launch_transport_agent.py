#!/usr/bin/env python3
"""
Example: Launch a transport agent on this machine.

Run this on each musician's machine to enable coordinated transport control.
"""

import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import QTimer

from skeleton_app.audio.transport_services import TransportAgentService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentWindow(QMainWindow):
    """Simple window for transport agent."""
    
    def __init__(self, node_id: str, osc_port: int = 5555):
        super().__init__()
        self.setWindowTitle(f"Transport Agent - {node_id}")
        self.resize(400, 300)
        
        # Create service
        try:
            self.service = TransportAgentService(
                node_id=node_id,
                jack_client_name=f"transport_agent_{node_id}",
                osc_port=osc_port
            )
            
            # Import widget
            from skeleton_app.gui.widgets.transport_nodes import TransportAgentNodeWidget
            
            # Create UI
            central = QWidget()
            layout = QVBoxLayout(central)
            
            self.node_widget = TransportAgentNodeWidget(self.service)
            layout.addWidget(self.node_widget)
            
            self.setCentralWidget(central)
            
            # Start service
            QTimer.singleShot(100, self.service.start)
            
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            raise
    
    def closeEvent(self, event):
        """Clean shutdown."""
        if hasattr(self, 'service'):
            self.service.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Get node ID from command line or use hostname
    import socket
    node_id = sys.argv[1] if len(sys.argv) > 1 else socket.gethostname()
    
    # Get OSC port from command line or use default
    osc_port = int(sys.argv[2]) if len(sys.argv) > 2 else 5555
    
    window = AgentWindow(node_id, osc_port)
    window.show()
    
    logger.info(f"Transport agent running on OSC port {osc_port}")
    logger.info("This agent will respond to OSC commands from a coordinator")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
