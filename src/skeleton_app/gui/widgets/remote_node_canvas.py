"""
Remote Node Canvas - visual JACK graph for remote cluster nodes.

Similar to NodeCanvasWidget but queries remote JACK state via SSH.
Completely replaces its contents when a different node is selected.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton
)
from PySide6.QtCore import Signal

from skeleton_app.gui.widgets.node_canvas_v3 import GraphModel, GraphCanvas, PortModel

logger = logging.getLogger(__name__)


class RemoteNodeCanvas(QWidget):
    """
    Remote node canvas for visualizing JACK graphs on cluster nodes.
    
    Hot-swappable: entire contents update when selecting different nodes.
    """
    
    node_changed = Signal(str)  # Emitted when node selection changes
    
    def __init__(self, parent: Optional[QWidget] = None, tool_registry=None, config=None):
        super().__init__(parent)
        self.tool_registry = tool_registry
        self.config = config
        self.current_node_id: Optional[str] = None
        self.current_node_name: Optional[str] = None
        self.current_node_host: Optional[str] = None
        self.available_nodes: Dict = {}
        
        # Model and view
        self.model = GraphModel()
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        
        # Controls
        controls = QHBoxLayout()
        
        # Node selector
        node_label = QLabel("Remote Node:")
        controls.addWidget(node_label)
        
        self.node_selector = QComboBox()
        self.node_selector.currentTextChanged.connect(self._on_node_selected)
        controls.addWidget(self.node_selector)
        
        controls.addStretch()
        
        # Title
        self.title_label = QLabel("Remote Node Canvas")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        controls.addWidget(self.title_label)
        
        controls.addStretch()
        
        # Refresh button
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._on_refresh_clicked)
        controls.addWidget(btn_refresh)
        
        layout.addLayout(controls)
        
        # Canvas view
        self.canvas = GraphCanvas(self.model)
        layout.addWidget(self.canvas)
        
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
        
        # Store node info
        self.available_nodes = {node['node_id']: node for node in nodes}
        
        # Populate dropdown
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
        """Handle node selection change - completely refresh canvas."""
        if not node_name:
            return
        
        node_id = self.node_selector.currentData()
        self.current_node_id = node_id
        self.current_node_name = node_name
        
        # Get host from available_nodes
        if node_id in self.available_nodes:
            self.current_node_host = self.available_nodes[node_id].get('host')
        
        self.title_label.setText(f"Remote Node Canvas - {node_name}")
        self.node_changed.emit(node_id)
        
        # Fetch this node's JACK state
        self._sync_update_canvas()
    
    def _on_refresh_clicked(self):
        """Refresh button clicked."""
        self._sync_update_canvas()
    
    def _sync_update_canvas(self):
        """Synchronously update canvas from remote node."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._update_canvas())
            loop.close()
        except Exception as e:
            logger.error(f"Error updating canvas: {e}")
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    async def _update_canvas(self):
        """Fetch and update canvas from remote node."""
        if not self.current_node_id:
            self.status_label.setText("No node selected")
            self.status_label.setStyleSheet("color: gray;")
            return
        
        # Check if this is the local node
        is_local_node = (self.config and self.current_node_id == self.config.node.id)
        
        try:
            if is_local_node:
                # Query local JACK via tool registry
                logger.info(f"Querying local JACK for node {self.current_node_id}")
                result = await self.tool_registry.execute(
                    "jack_status",
                    {},
                    requester=f"remote_canvas:{self.current_node_id}"
                )
            else:
                # Query remote JACK via SSH
                if not self.current_node_host:
                    self.status_label.setText(f"No host configured for node {self.current_node_name}")
                    self.status_label.setStyleSheet("color: red;")
                    return
                
                logger.info(f"Querying remote JACK for node {self.current_node_name} at {self.current_node_host}")
                result = await self._query_remote_jack()
            
            if result['status'] == 'success':
                self._populate_canvas(result['output'])
                self.status_label.setText(f"Connected - {self.current_node_name}")
                self.status_label.setStyleSheet("color: green;")
                logger.info(f"Successfully updated canvas for {self.current_node_name}")
            else:
                error_msg = result.get('error', 'Unknown error')
                self.status_label.setText(f"Error: {error_msg}")
                self.status_label.setStyleSheet("color: red;")
                logger.error(f"Failed to query {self.current_node_name}: {error_msg}")
        
        except Exception as e:
            logger.error(f"Failed to update canvas for {self.current_node_name}: {e}", exc_info=True)
            self.status_label.setText(f"Error: {e}")
            self.status_label.setStyleSheet("color: red;")
    
    async def _query_remote_jack(self) -> Dict[str, Any]:
        """Query remote node's JACK status via SSH."""
        if not self.current_node_host:
            return {
                "status": "error",
                "error": "Remote node host not available"
            }
        
        from skeleton_app.remote import SSHExecutor
        
        executor = SSHExecutor()
        
        try:
            # Execute jack_lsp on remote node
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
            output_ports = set()
            input_ports = set()
            connections = {}
            
            current_port = None
            for line in stdout.strip().split('\n'):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                if line.startswith(' '):
                    # This is a connection (indented line)
                    if current_port:
                        connected_port = line_stripped
                        if current_port not in connections:
                            connections[current_port] = []
                        connections[current_port].append(connected_port)
                else:
                    # This is a port name
                    current_port = line_stripped
                    
                    # Classify as output or input
                    if '_in' in current_port.lower() or ':in' in current_port.lower():
                        input_ports.add(current_port)
                    elif '_out' in current_port.lower() or ':out' in current_port.lower():
                        output_ports.add(current_port)
                    elif 'capture' in current_port.lower():
                        output_ports.add(current_port)
                    elif 'playback' in current_port.lower():
                        input_ports.add(current_port)
                    else:
                        input_ports.add(current_port)
            
            return {
                "status": "success",
                "output": {
                    "ports": {
                        "output": sorted(list(output_ports)),
                        "input": sorted(list(input_ports)),
                        "total": len(output_ports) + len(input_ports)
                    },
                    "connections": connections
                }
            }
        
        except Exception as e:
            logger.error(f"SSH query failed: {e}")
            return {
                "status": "error",
                "error": f"SSH query failed: {str(e)}"
            }
    
    def _populate_canvas(self, jack_state: dict):
        """Populate canvas from remote JACK state - completely replace contents."""
        # Clear existing model
        self.model.begin_batch()
        self.model.clear()
        
        # Parse port state
        ports_dict = jack_state.get('ports', {})
        output_ports_list = ports_dict.get('output', []) if isinstance(ports_dict, dict) else []
        input_ports_list = ports_dict.get('input', []) if isinstance(ports_dict, dict) else []
        connections = jack_state.get('connections', {})
        
        # Create set for quick lookup
        output_ports_set = set(output_ports_list)
        
        # Group ports by client (use ALL ports like local canvas does)
        clients = {}
        # Use set to avoid duplicates
        all_ports = set(output_ports_list + input_ports_list)
        
        for port_name in all_ports:
            if ':' not in port_name:
                continue
            
            client_name = port_name.split(':')[0]
            port_short = ':'.join(port_name.split(':')[1:])
            is_output = port_name in output_ports_set
            
            if client_name not in clients:
                clients[client_name] = []
            clients[client_name].append((port_short, port_name, is_output))
        
        # Create nodes with auto-layout
        x, y = 50, 50
        for client_name, ports in clients.items():
            # Split special clients like local canvas does
            if client_name == "system":
                # Split system by checking port SHORT names
                capture_ports = [(s, f) for s, f, _ in ports if "capture" in s]
                playback_ports = [(s, f) for s, f, _ in ports if "playback" in s]
                
                if capture_ports:
                    node_name = "system (capture)"
                    node = self.model.add_node(node_name, x, y)
                    for port_short, port_full in capture_ports:
                        node.outputs.append(PortModel(port_short, port_full, True))
                    y += 150
                
                if playback_ports:
                    node_name = "system (playback)"
                    node = self.model.add_node(node_name, x, y)
                    for port_short, port_full in playback_ports:
                        node.inputs.append(PortModel(port_short, port_full, False))
                    y += 150
            
            elif client_name.startswith("a2j"):
                # Split a2j clients into capture (sources) and playback (sinks)
                capture_ports = [(s, f) for s, f, is_out in ports if is_out]
                playback_ports = [(s, f) for s, f, is_out in ports if not is_out]
                
                if capture_ports:
                    node_name = f"{client_name} (capture)"
                    node = self.model.add_node(node_name, x, y)
                    for port_short, port_full in capture_ports:
                        node.outputs.append(PortModel(port_short, port_full, True))
                    y += 150
                
                if playback_ports:
                    node_name = f"{client_name} (playback)"
                    node = self.model.add_node(node_name, x, y)
                    for port_short, port_full in playback_ports:
                        node.inputs.append(PortModel(port_short, port_full, False))
                    y += 150
            
            else:
                # Regular client - keep all ports together
                node = self.model.add_node(client_name, x, y)
                for port_short, port_full, is_output in ports:
                    if is_output:
                        node.outputs.append(PortModel(port_short, port_full, True))
                    else:
                        node.inputs.append(PortModel(port_short, port_full, False))
                
                x += 200
                if x > 800:
                    x = 50
                    y += 150
        
        # Add connections (like local canvas does)
        for out_port, in_ports in connections.items():
            if isinstance(in_ports, list):
                for in_port in in_ports:
                    self.model.add_connection(out_port, in_port)
            elif isinstance(in_ports, str):
                self.model.add_connection(out_port, in_ports)
        
        # End batch - trigger rebuild
        self.model.end_batch()
