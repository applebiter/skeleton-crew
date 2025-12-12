"""
Cluster status panel widget.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer


class ClusterPanel(QWidget):
    """
    Displays status of cluster nodes.
    
    Shows:
    - Online/offline nodes
    - Node capabilities
    - Current load
    - Agent activity
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self._setup_ui()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status)
        self.update_timer.start(5000)  # Update every 5 seconds
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Cluster Nodes")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Node tree
        self.node_tree = QTreeWidget()
        self.node_tree.setHeaderLabels(["Node", "Status", "Load"])
        self.node_tree.setColumnWidth(0, 150)
        layout.addWidget(self.node_tree)
        
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
        """Update cluster node status."""
        # TODO: Implement actual cluster status fetching
        # For now, just placeholder
        self.node_tree.clear()
        
        # Add local node
        local_item = QTreeWidgetItem(["Local", "● Online", "25%"])
        local_item.setForeground(1, Qt.green)
        self.node_tree.addTopLevelItem(local_item)
        
        # Add placeholder remote nodes
        for i in range(3):
            item = QTreeWidgetItem([f"node-{i+1}", "○ Offline", "—"])
            item.setForeground(1, Qt.gray)
            self.node_tree.addTopLevelItem(item)
