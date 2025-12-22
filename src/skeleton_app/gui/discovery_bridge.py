"""
Thread-safe bridge between async service discovery and Qt GUI.

The service discovery runs in a separate async thread, while the GUI runs in the Qt main thread.
This module provides Qt signals that allow safe communication between them without blocking either.
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import QObject, Signal


class ServiceDiscoveryBridge(QObject):
    """
    Qt-based signal bridge for service discovery events.
    
    This allows the async service discovery thread to emit signals that are
    safely handled by the Qt GUI main thread without blocking.
    """
    
    # Signals (must be class variables)
    node_discovered = Signal(str, str, str)  # (node_id, node_name, host)
    service_registered = Signal(str, str, str, str)  # (node_id, service_name, service_type, action)
    service_updated = Signal(str, str, str, str)  # (node_id, service_name, service_type, action)
    service_unregistered = Signal(str, str)  # (node_id, service_name)
    services_loaded = Signal()  # Initial services loaded from DB
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.discovery = None
    
    def set_discovery(self, discovery):
        """Store reference to discovery instance."""
        self.discovery = discovery
    
    def emit_node_discovered(self, node_id: str, node_name: str, host: str):
        """Safely emit node discovery from any thread."""
        self.node_discovered.emit(node_id, node_name, host)
    
    def emit_service_registered(self, node_id: str, service_name: str, service_type: str, action: str):
        """Safely emit service registration from any thread."""
        self.service_registered.emit(node_id, service_name, service_type, action)
    
    def emit_service_updated(self, node_id: str, service_name: str, service_type: str, action: str):
        """Safely emit service update from any thread."""
        self.service_updated.emit(node_id, service_name, service_type, action)
    
    def emit_service_unregistered(self, node_id: str, service_name: str):
        """Safely emit service unregistration from any thread."""
        self.service_unregistered.emit(node_id, service_name)
    
    def emit_services_loaded(self):
        """Safely emit initial services loaded from any thread."""
        self.services_loaded.emit()
