"""
Cluster status panel widget.
"""

from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QHBoxLayout, QGroupBox
)
from PySide6.QtCore import Qt, QTimer

from skeleton_app.service_discovery import ServiceDiscovery, ServiceInfo, ServiceType


class ClusterPanel(QWidget):
    """
    Displays status of cluster nodes and their services.
    
    Shows:
    - Online/offline nodes
    - Available services per node
    - Service health status
    - Service capabilities
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.service_discovery: Optional[ServiceDiscovery] = None
        
        self._setup_ui()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status)
        self.update_timer.start(2000)  # Update every 2 seconds
    
    def set_service_discovery(self, service_discovery: Optional[ServiceDiscovery]):
        """Set the service discovery instance."""
        self.service_discovery = service_discovery
        if service_discovery:
            # Add callback for service changes
            service_discovery.add_callback(self._on_service_change)
        self._update_status()
    
    def _on_service_change(self, action: str, service: ServiceInfo):
        """Handle service change notifications."""
        # Trigger update on next timer tick
        pass
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Cluster Services")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Service tree (grouped by node)
        self.service_tree = QTreeWidget()
        self.service_tree.setHeaderLabels(["Node / Service", "Type", "Status"])
        self.service_tree.setColumnWidth(0, 200)
        self.service_tree.setColumnWidth(1, 120)
        layout.addWidget(self.service_tree)
        
        # Stats group
        stats_group = QGroupBox("Cluster Summary")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("No data")
        stats_layout.addWidget(self.stats_label)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Refresh button
        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._update_status)
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Initial update
        self._update_status()
    
    def _update_status(self):
        """Update cluster service status."""
        if not self.service_discovery:
            self.service_tree.clear()
            self.stats_label.setText("Service discovery not initialized")
            return
        
        self.service_tree.clear()
        
        # Get all services grouped by node
        all_services = self.service_discovery.get_all_services()
        
        total_services = 0
        healthy_services = 0
        service_types_count: Dict[ServiceType, int] = {}
        
        # Group services by node
        for node_id, services in all_services.items():
            if not services:
                continue
            
            # Create node item
            node_item = QTreeWidgetItem([node_id, "", ""])
            node_item.setExpanded(True)
            node_item.setForeground(0, Qt.white)
            
            # Add services under node
            for service in services:
                total_services += 1
                
                # Count by type
                service_types_count[service.service_type] = service_types_count.get(service.service_type, 0) + 1
                
                # Status indicator
                if service.health_status.value == "healthy":
                    status_icon = "●"
                    status_color = Qt.green
                    healthy_services += 1
                elif service.health_status.value == "degraded":
                    status_icon = "◐"
                    status_color = Qt.yellow
                else:
                    status_icon = "○"
                    status_color = Qt.red
                
                # Format service type
                service_type_display = service.service_type.value.replace('_', ' ').title()
                
                # Create service item
                service_item = QTreeWidgetItem([
                    f"  {service.service_name}",
                    service_type_display,
                    f"{status_icon} {service.status.value.capitalize()}"
                ])
                service_item.setForeground(2, status_color)
                
                # Add tooltip with details
                tooltip = f"Type: {service_type_display}\n"
                tooltip += f"Status: {service.status.value}\n"
                tooltip += f"Health: {service.health_status.value}\n"
                if service.endpoint:
                    tooltip += f"Endpoint: {service.endpoint}\n"
                if service.port:
                    tooltip += f"Port: {service.port}\n"
                if service.capabilities:
                    tooltip += f"Capabilities: {', '.join(str(k) for k in service.capabilities.keys())}\n"
                
                service_item.setToolTip(0, tooltip)
                
                node_item.addChild(service_item)
            
            self.service_tree.addTopLevelItem(node_item)
        
        # Update stats
        stats_text = f"Nodes: {len(all_services)}\n"
        stats_text += f"Services: {total_services} total, {healthy_services} healthy\n\n"
        stats_text += "By Type:\n"
        for service_type, count in sorted(service_types_count.items(), key=lambda x: -x[1]):
            type_display = service_type.value.replace('_', ' ').title()
            stats_text += f"  • {type_display}: {count}\n"
        
        self.stats_label.setText(stats_text)
        
        # If no services, show message
        if total_services == 0:
            placeholder = QTreeWidgetItem(["No services discovered", "", ""])
            placeholder.setForeground(0, Qt.gray)
            self.service_tree.addTopLevelItem(placeholder)
