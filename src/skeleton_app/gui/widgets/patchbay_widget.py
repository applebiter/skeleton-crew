"""
JACK patchbay visual widget.
"""

from typing import Optional, Dict, Set, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem,
    QSplitter, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal

from skeleton_app.audio.jack_client import JackClientManager


class PatchbayWidget(QWidget):
    """
    Visual JACK patchbay.
    
    Shows audio ports and connections, allows connecting/disconnecting.
    Similar to QJackCtl but integrated into skeleton-app.
    """
    
    # Signals
    connection_made = Signal(str, str)  # output_port, input_port
    connection_broken = Signal(str, str)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jack_manager: Optional[JackClientManager] = None
        
        # Track current connections
        self.connections: Dict[str, Set[str]] = {}
        
        self._setup_ui()
        
        # Update timer - DISABLED by default for real-time work
        # User can manually refresh as needed
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_ports)
        # Don't start automatically - manual refresh only
        
        self._auto_refresh_enabled = False
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        
        # Title and controls
        header = QHBoxLayout()
        title = QLabel("JACK Patchbay")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(title)
        
        header.addStretch()
        
        self.auto_refresh_button = QPushButton("Auto-Refresh: OFF")
        self.auto_refresh_button.setCheckable(True)
        self.auto_refresh_button.clicked.connect(self._toggle_auto_refresh)
        header.addWidget(self.auto_refresh_button)
        
        self.connect_button = QPushButton("Connect Selected")
        self.connect_button.clicked.connect(self._connect_selected)
        self.connect_button.setEnabled(False)
        header.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect Selected")
        self.disconnect_button.clicked.connect(self._disconnect_selected)
        self.disconnect_button.setEnabled(False)
        header.addWidget(self.disconnect_button)
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._update_ports)
        header.addWidget(self.refresh_button)
        
        layout.addLayout(header)
        
        # Port lists
        splitter = QSplitter(Qt.Horizontal)
        
        # Output ports (left) - these PRODUCE audio (e.g., "capture" devices)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        
        output_label = QLabel("Output Ports (Capture/Sources)")
        output_label.setStyleSheet("font-weight: bold;")
        output_layout.addWidget(output_label)
        
        self.output_tree = QTreeWidget()
        self.output_tree.setHeaderLabels(["Port", "Connected To"])
        self.output_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.output_tree.itemExpanded.connect(self._on_item_expanded)
        self.output_tree.itemCollapsed.connect(self._on_item_collapsed)
        output_layout.addWidget(self.output_tree)
        
        splitter.addWidget(output_widget)
        
        # Input ports (right) - these CONSUME audio (e.g., "playback" devices)
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        input_label = QLabel("Input Ports (Playback/Sinks)")
        input_label.setStyleSheet("font-weight: bold;")
        input_layout.addWidget(input_label)
        
        self.input_tree = QTreeWidget()
        self.input_tree.setHeaderLabels(["Port"])
        self.input_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.input_tree.itemExpanded.connect(self._on_item_expanded)
        self.input_tree.itemCollapsed.connect(self._on_item_collapsed)
        input_layout.addWidget(self.input_tree)
        
        splitter.addWidget(input_widget)
        
        layout.addWidget(splitter)
        
        # Status label
        self.status_label = QLabel("Not connected to JACK")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)
    
    def set_jack_manager(self, jack_manager: Optional[JackClientManager]):
        """
        Set the JACK client manager.
        
        Args:
            jack_manager: JACK client manager instance
        """
        self.jack_manager = jack_manager
        
        if jack_manager:
            self.status_label.setText(f"Connected - {jack_manager.sample_rate} Hz, {jack_manager.buffer_size} frames")
            self.status_label.setStyleSheet("color: green;")
            self._update_ports()
        else:
            self.status_label.setText("Not connected to JACK")
            self.status_label.setStyleSheet("color: gray;")
            self.output_tree.clear()
            self.input_tree.clear()
    
    def _toggle_auto_refresh(self, checked: bool):
        """Toggle automatic refresh."""
        self._auto_refresh_enabled = checked
        if checked:
            self.auto_refresh_button.setText("Auto-Refresh: ON")
            self.update_timer.start(5000)  # Every 5 seconds when enabled
        else:
            self.auto_refresh_button.setText("Auto-Refresh: OFF")
            self.update_timer.stop()
    
    def _on_item_expanded(self, item):
        """Handle item expansion."""
        pass
    
    def _on_item_collapsed(self, item):
        """Handle item collapse."""
        pass
    
    def _update_ports(self):
        """Update port lists and connections."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            return
        
        # Save expanded state before clearing
        output_expanded = set()
        for i in range(self.output_tree.topLevelItemCount()):
            item = self.output_tree.topLevelItem(i)
            if item.isExpanded():
                output_expanded.add(item.text(0))
        
        input_expanded = set()
        for i in range(self.input_tree.topLevelItemCount()):
            item = self.input_tree.topLevelItem(i)
            if item.isExpanded():
                input_expanded.add(item.text(0))
        
        # Get current connections
        self.connections = self.jack_manager.get_all_connections()
        
        # Update output ports (sources - they output audio)
        self.output_tree.clear()
        output_ports = self.jack_manager.get_ports(is_output=True, is_audio=True)
        print(f"DEBUG: Found {len(output_ports)} output ports (sources)")
        
        # Group by client
        output_clients: Dict[str, list] = {}
        for port in output_ports:
            client_name = port.split(':')[0]
            if client_name not in output_clients:
                output_clients[client_name] = []
            output_clients[client_name].append(port)
        
        # Add to tree
        for client_name in sorted(output_clients.keys()):
            client_item = QTreeWidgetItem([client_name, ""])
            # Always start collapsed - user expands what they want to see
            client_item.setExpanded(client_name in output_expanded)
            self.output_tree.addTopLevelItem(client_item)
            
            for port in sorted(output_clients[client_name]):
                # Get connected inputs
                connected = self.connections.get(port, [])
                connected_str = ", ".join([p.split(':')[1] for p in connected]) if connected else "—"
                
                port_item = QTreeWidgetItem([port.split(':')[1], connected_str])
                port_item.setData(0, Qt.UserRole, port)  # Store full port name
                client_item.addChild(port_item)
        
        # Update input ports (sinks - they consume audio)
        self.input_tree.clear()
        input_ports = self.jack_manager.get_ports(is_input=True, is_audio=True)
        print(f"DEBUG: Found {len(input_ports)} input ports (sinks)")
        
        # Group by client
        input_clients: Dict[str, list] = {}
        for port in input_ports:
            client_name = port.split(':')[0]
            if client_name not in input_clients:
                input_clients[client_name] = []
            input_clients[client_name].append(port)
        
        # Add to tree
        for client_name in sorted(input_clients.keys()):
            client_item = QTreeWidgetItem([client_name])
            # Always start collapsed - user expands what they want to see
            client_item.setExpanded(client_name in input_expanded)
            self.input_tree.addTopLevelItem(client_item)
            
            for port in sorted(input_clients[client_name]):
                port_item = QTreeWidgetItem([port.split(':')[1]])
                port_item.setData(0, Qt.UserRole, port)  # Store full port name
                client_item.addChild(port_item)
    
    def _on_selection_changed(self):
        """Handle selection change in port trees."""
        output_selected = len(self.output_tree.selectedItems()) > 0
        input_selected = len(self.input_tree.selectedItems()) > 0
        
        # Enable connect button if one output and one input selected
        can_connect = output_selected and input_selected
        self.connect_button.setEnabled(can_connect)
        
        # Enable disconnect button if output port is selected and has connections
        can_disconnect = False
        if output_selected:
            item = self.output_tree.selectedItems()[0]
            if item.parent():  # Is a port, not a client
                port = item.data(0, Qt.UserRole)
                can_disconnect = port in self.connections and len(self.connections[port]) > 0
        
        self.disconnect_button.setEnabled(can_disconnect)
    
    def _connect_selected(self):
        """Connect selected output to selected input."""
        if not self.jack_manager:
            return
        
        output_items = self.output_tree.selectedItems()
        input_items = self.input_tree.selectedItems()
        
        if not output_items or not input_items:
            return
        
        output_item = output_items[0]
        input_item = input_items[0]
        
        # Get port names (skip if client is selected)
        if not output_item.parent() or not input_item.parent():
            return
        
        output_port = output_item.data(0, Qt.UserRole)
        input_port = input_item.data(0, Qt.UserRole)
        
        try:
            self.jack_manager.connect_ports(output_port, input_port)
            self.connection_made.emit(output_port, input_port)
            self._update_ports()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Connection Failed",
                f"Failed to connect ports:\n{e}"
            )
    
    def _disconnect_selected(self):
        """Disconnect selected output from its connections."""
        if not self.jack_manager:
            return
        
        output_items = self.output_tree.selectedItems()
        if not output_items:
            return
        
        output_item = output_items[0]
        if not output_item.parent():  # Skip if client is selected
            return
        
        output_port = output_item.data(0, Qt.UserRole)
        
        # Get connections for this port
        connected = self.connections.get(output_port, [])
        if not connected:
            return
        
        # Disconnect all
        for input_port in connected:
            try:
                self.jack_manager.disconnect_ports(output_port, input_port)
                self.connection_broken.emit(output_port, input_port)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Disconnection Failed",
                    f"Failed to disconnect {output_port} from {input_port}:\n{e}"
                )
        
        self._update_ports()
