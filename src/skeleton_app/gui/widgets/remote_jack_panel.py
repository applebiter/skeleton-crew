"""
Remote JACK patchbay widget for manipulating audio graphs on cluster nodes.

Provides identical interface to local patchbay but executes operations
on remote machines via tool registry over ZeroMQ.
"""

import logging
from typing import Optional, Dict, Set, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem,
    QSplitter, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal

from skeleton_app.providers.tools import ToolRegistry

logger = logging.getLogger(__name__)


class RemoteJackPanel(QWidget):
    """
    Remote JACK patchbay for controlling audio graphs on cluster nodes.
    
    Provides identical UI/UX to local patchbay but operates on remote JACK servers
    via tool execution. Allows users to view and manipulate any node's audio graph
    from any machine in the cluster.
    """
    
    # Signals
    connection_made = Signal(str, str, str)  # node_id, output_port, input_port
    connection_broken = Signal(str, str, str)
    node_changed = Signal(str)  # When user switches to different node
    
    def __init__(self, parent: Optional[QWidget] = None, tool_registry: Optional[ToolRegistry] = None):
        super().__init__(parent)
        self.tool_registry = tool_registry
        self.current_node_id: Optional[str] = None
        self.current_node_name: Optional[str] = None
        self.current_node_host: Optional[str] = None  # Host IP for SSH
        self.available_nodes: Dict = {}  # node_id -> {node_id, node_name, host, ...}
        
        # Track current connections on remote node
        self.connections: Dict[str, Set[str]] = {}
        
        self._setup_ui()
        
        # Update timer for remote port state
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_update_timer)
        self._auto_refresh_enabled = False
    
    def _on_update_timer(self):
        """Timer callback - update ports on main thread (JACK is not thread-safe)."""
        self._sync_update_ports()
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        
        # Node selector and controls
        header = QHBoxLayout()
        
        # Node selector dropdown
        node_label = QLabel("Remote Node:")
        header.addWidget(node_label)
        
        self.node_selector = QComboBox()
        self.node_selector.currentTextChanged.connect(self._on_node_selected)
        header.addWidget(self.node_selector)
        
        header.addStretch()
        
        # Title
        self.title_label = QLabel("Remote JACK Patchbay")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self.title_label)
        
        header.addStretch()
        
        # Controls
        self.auto_refresh_button = QPushButton("Auto-Refresh: OFF")
        self.auto_refresh_button.setCheckable(True)
        self.auto_refresh_button.clicked.connect(self._toggle_auto_refresh)
        header.addWidget(self.auto_refresh_button)
        
        self.connect_button = QPushButton("Connect Selected")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.connect_button.setEnabled(False)
        header.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect Selected")
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        header.addWidget(self.disconnect_button)
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        header.addWidget(self.refresh_button)
        
        layout.addLayout(header)
        
        # Port lists (same layout as local patchbay)
        splitter = QSplitter(Qt.Horizontal)
        
        # Output ports (left)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        
        output_label = QLabel("Output Ports (Capture/Sources)")
        output_label.setStyleSheet("font-weight: bold;")
        output_layout.addWidget(output_label)
        
        self.output_tree = QTreeWidget()
        self.output_tree.setHeaderLabels(["Port", "Connected To"])
        self.output_tree.itemSelectionChanged.connect(self._on_selection_changed)
        output_layout.addWidget(self.output_tree)
        
        splitter.addWidget(output_widget)
        
        # Input ports (right)
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        input_label = QLabel("Input Ports (Playback/Sinks)")
        input_label.setStyleSheet("font-weight: bold;")
        input_layout.addWidget(input_label)
        
        self.input_tree = QTreeWidget()
        self.input_tree.setHeaderLabels(["Port"])
        self.input_tree.itemSelectionChanged.connect(self._on_selection_changed)
        input_layout.addWidget(self.input_tree)
        
        splitter.addWidget(input_widget)
        
        layout.addWidget(splitter)
        
        # Status label
        self.status_label = QLabel("Select a node to view its JACK graph")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)
    
    def set_available_nodes(self, nodes: list):
        """
        Update the list of available nodes to choose from.
        
        Args:
            nodes: List of dicts with 'node_id', 'node_name', 'host' keys
        """
        self.node_selector.blockSignals(True)
        self.node_selector.clear()
        
        # Store node info for later use (especially host for SSH)
        self.available_nodes = {node['node_id']: node for node in nodes}
        
        for node in nodes:
            self.node_selector.addItem(
                node['node_name'],
                userData=node['node_id']
            )
        
        self.node_selector.blockSignals(False)
        
        if nodes:
            self.node_selector.setCurrentIndex(0)
            self._on_node_selected(self.node_selector.currentText())
    
    def _on_node_selected(self, node_name: str):
        """Handle node selection change."""
        if not node_name:
            return
        
        node_id = self.node_selector.currentData()
        self.current_node_id = node_id
        self.current_node_name = node_name
        
        # Get host from available_nodes
        if node_id in self.available_nodes:
            self.current_node_host = self.available_nodes[node_id].get('host')
        
        self.title_label.setText(f"Remote JACK Patchbay - {node_name}")
        self.node_changed.emit(node_id)
        
        # Fetch this node's JACK state (run synchronously - JACK is not thread-safe)
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._update_ports())
            loop.close()
        except Exception as e:
            logger.error(f"Error updating ports: {e}")
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    async def _update_ports(self):
        """Fetch and update port list from remote node."""
        if not self.current_node_id or not self.tool_registry:
            self.status_label.setText("No node selected or tool registry unavailable")
            return
        
        # Check if this is the local node or a remote node
        from skeleton_app.config import get_settings
        settings = get_settings()
        is_local_node = (self.current_node_id == settings.node.id)
        
        try:
            if is_local_node:
                # Query local JACK server via tool registry
                result = await self.tool_registry.execute(
                    "jack_status",
                    {},
                    requester=f"remote_jack_panel:{self.current_node_id}"
                )
            else:
                # Query remote JACK server via SSH
                result = await self._query_remote_jack_status()
            
            if result['status'] == 'success':
                output = result['output']
                self._populate_ports(output)
                self.status_label.setText(f"Connected - {self.current_node_name}")
                self.status_label.setStyleSheet("color: green;")
            else:
                self.status_label.setText(f"Error fetching JACK state: {result.get('error')}")
                self.status_label.setStyleSheet("color: red;")
        except Exception as e:
            logger.error(f"Failed to update remote ports: {e}")
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    async def _query_remote_jack_status(self) -> Dict[str, Any]:
        """Query remote node's JACK status via SSH."""
        if not self.current_node_host:
            return {
                "status": "error",
                "error": "Remote node host not available"
            }
        
        from skeleton_app.remote import SSHExecutor
        
        executor = SSHExecutor()
        
        try:
            # Execute jack_lsp on remote node to get ports
            exit_code, stdout, stderr = await executor.execute(
                self.current_node_host,
                "jack_lsp -c"  # -c for connections
            )
            
            if exit_code != 0:
                return {
                    "status": "error",
                    "error": f"SSH command failed: {stderr}"
                }
            
            # Parse jack_lsp output
            output_ports = []
            input_ports = []
            connections = {}
            
            current_port = None
            for line in stdout.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Port format: "system:capture_1" (possibly with indentation for connections)
                if line.startswith(' '):
                    # This is a connection (indented)
                    if current_port:
                        connected_port = line.strip()
                        if current_port not in connections:
                            connections[current_port] = []
                        connections[current_port].append(connected_port)
                else:
                    # This is a port name
                    current_port = line
                    
                    # Classify as input or output
                    if 'capture' in line.lower() or ':out' in line.lower():
                        output_ports.append(line)
                    else:
                        input_ports.append(line)
            
            return {
                "status": "success",
                "output": {
                    "ports": {
                        "output": output_ports,
                        "input": input_ports,
                        "total": len(output_ports) + len(input_ports)
                    },
                    "connections": connections,
                    "transport_state": "unknown",
                    "sample_rate": 44100,
                    "buffer_size": 256
                }
            }
        except Exception as e:
            logger.error(f"SSH query failed: {e}")
            return {
                "status": "error",
                "error": f"SSH query failed: {str(e)}"
            }
    
    def _populate_ports(self, jack_state: dict):
        """Populate the port trees from remote JACK state."""
        self.output_tree.clear()
        self.input_tree.clear()
        self.connections.clear()
        
        # Parse port state from remote node
        # jack_state format: {status, ports: {output: [...], input: [...]}, connections: {...}, ...}
        ports_dict = jack_state.get('ports', {})
        output_ports = ports_dict.get('output', []) if isinstance(ports_dict, dict) else []
        input_ports = ports_dict.get('input', []) if isinstance(ports_dict, dict) else []
        
        connections = jack_state.get('connections', {})
        
        # Build connection map from the connections dict
        # Format: {source_port: [dest_port1, dest_port2, ...], ...}
        for source_port, dest_ports in connections.items():
            if source_port not in self.connections:
                self.connections[source_port] = set()
            if isinstance(dest_ports, list):
                self.connections[source_port].update(dest_ports)
            elif isinstance(dest_ports, str):
                self.connections[source_port].add(dest_ports)
        
        # Add output ports (sources/capture)
        for port_name in output_ports:
            port_item = QTreeWidgetItem([port_name, ""])
            port_item.setData(0, Qt.UserRole, port_name)
            
            # Show connections for this port
            if port_name in self.connections:
                for connected_port in self.connections[port_name]:
                    conn_item = QTreeWidgetItem([connected_port])
                    port_item.addChild(conn_item)
            
            self.output_tree.addTopLevelItem(port_item)
        
        # Add input ports (sinks/playback)
        for port_name in input_ports:
            port_item = QTreeWidgetItem([port_name])
            port_item.setData(0, Qt.UserRole, port_name)
            self.input_tree.addTopLevelItem(port_item)
    
    def _on_selection_changed(self):
        """Update button states based on selection."""
        output_selected = bool(self.output_tree.selectedItems())
        input_selected = bool(self.input_tree.selectedItems())
        
        # Need both output and input selected to connect
        self.connect_button.setEnabled(output_selected and input_selected)
        self.disconnect_button.setEnabled(output_selected or input_selected)
    
    def _sync_update_ports(self):
        """Synchronously update ports (JACK must be called from main thread)."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._update_ports())
            loop.close()
        except Exception as e:
            logger.error(f"Failed to update ports: {e}")
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    def _sync_connect_selected(self):
        """Synchronously connect selected ports."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._connect_selected())
            loop.close()
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            QMessageBox.critical(self, "Connection Error", str(e))
    
    def _sync_disconnect_selected(self):
        """Synchronously disconnect selected ports."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._disconnect_selected())
            loop.close()
        except Exception as e:
            logger.error(f"Disconnection failed: {e}")
            QMessageBox.critical(self, "Disconnection Error", str(e))
    
    def _on_refresh_clicked(self):
        """Refresh button clicked - update ports on main thread."""
        self._sync_update_ports()
    
    def _on_connect_clicked(self):
        """Connect button clicked - connect ports on main thread."""
        self._sync_connect_selected()
    
    def _on_disconnect_clicked(self):
        """Disconnect button clicked - disconnect ports on main thread."""
        self._sync_disconnect_selected()
    
    async def _connect_selected(self):
        """Connect selected output port to selected input port on remote node."""
        if not self.current_node_id or not self.tool_registry:
            return
        
        output_items = self.output_tree.selectedItems()
        input_items = self.input_tree.selectedItems()
        
        if not output_items or not input_items:
            QMessageBox.warning(self, "Selection Error", 
                              "Select one output and one input port to connect")
            return
        
        source_port = output_items[0].data(0, Qt.UserRole)
        dest_port = input_items[0].data(0, Qt.UserRole)
        
        try:
            result = await self.tool_registry.execute(
                "connect_jack_ports",
                {"source": source_port, "destination": dest_port},
                requester=f"remote_jack_panel:{self.current_node_id}"
            )
            
            if result['status'] == 'success':
                self.connection_made.emit(self.current_node_id, source_port, dest_port)
                self._update_ports()
            else:
                QMessageBox.critical(self, "Connection Failed", 
                                   f"Error: {result.get('error')}")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            QMessageBox.critical(self, "Connection Error", str(e))
    
    async def _disconnect_selected(self):
        """Disconnect selected ports on remote node."""
        if not self.current_node_id or not self.tool_registry:
            return
        
        selected = self.output_tree.selectedItems() or self.input_tree.selectedItems()
        
        if not selected:
            QMessageBox.warning(self, "Selection Error",
                              "Select a port to disconnect")
            return
        
        port_name = selected[0].data(0, Qt.UserRole)
        
        # Find all connections for this port and disconnect them
        try:
            if port_name in self.connections:
                for connected_port in list(self.connections[port_name]):
                    result = await self.tool_registry.execute(
                        "disconnect_jack_ports",
                        {"source": port_name, "destination": connected_port},
                        requester=f"remote_jack_panel:{self.current_node_id}"
                    )
                    
                    if result['status'] == 'success':
                        self.connection_broken.emit(self.current_node_id, port_name, connected_port)
            
            self._update_ports()
        except Exception as e:
            logger.error(f"Disconnection failed: {e}")
            QMessageBox.critical(self, "Disconnection Error", str(e))
    
    def _toggle_auto_refresh(self, checked: bool):
        """Toggle automatic refresh of remote port state."""
        self._auto_refresh_enabled = checked
        if checked:
            self.auto_refresh_button.setText("Auto-Refresh: ON")
            self.update_timer.start(5000)
        else:
            self.auto_refresh_button.setText("Auto-Refresh: OFF")
            self.update_timer.stop()
