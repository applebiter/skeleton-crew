"""
Remote Node Canvas - visual JACK graph for remote cluster nodes.

Similar to NodeCanvasWidget but queries remote JACK state via SSH.
Completely replaces its contents when a different node is selected.
"""

import logging
import json
from typing import Optional, Dict, Any
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton,
    QInputDialog, QMessageBox
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
        
        # Presets directory (per-host presets)
        self.presets_dir = Path.home() / ".config" / "skeleton-app" / "remote-jack-presets"
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        
        # Preset positions to apply
        self._preset_positions = {}
        
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
        
        # Preset controls
        controls.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        controls.addWidget(self.preset_combo)
        
        btn_save = QPushButton("💾 Save")
        btn_save.clicked.connect(self._save_preset)
        controls.addWidget(btn_save)
        
        btn_load = QPushButton("📁 Load")
        btn_load.clicked.connect(self._load_preset)
        controls.addWidget(btn_load)
        
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
        
        # Canvas view - pass remote_canvas parent for remote operations
        self.canvas = RemoteGraphCanvas(self.model, remote_parent=self)
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
        
        # Refresh preset list for this host
        self._refresh_preset_list()
        
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
                    
                    # Classify as output or input (use if-elif to prevent duplication)
                    if 'capture' in current_port.lower():
                        output_ports.add(current_port)
                    elif 'playback' in current_port.lower():
                        input_ports.add(current_port)
                    elif '_out' in current_port.lower() or ':out' in current_port.lower():
                        output_ports.add(current_port)
                    elif '_in' in current_port.lower() or ':in' in current_port.lower():
                        input_ports.add(current_port)
                    else:
                        # Default to input for unknown ports
                        input_ports.add(current_port)
            
            # Natural sort function for port names (e.g., capture_1, capture_2, ...)
            import re
            def natural_sort_key(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
            
            return {
                "status": "success",
                "output": {
                    "ports": {
                        "output": sorted(list(output_ports), key=natural_sort_key),
                        "input": sorted(list(input_ports), key=natural_sort_key),
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
        
        # Create nodes with auto-layout (but restore preset positions if available)
        x, y = 50, 50
        for client_name, ports in clients.items():
            # Split special clients like local canvas does
            if client_name == "system":
                # Split system by checking port SHORT names
                capture_ports = [(s, f) for s, f, _ in ports if "capture" in s]
                playback_ports = [(s, f) for s, f, _ in ports if "playback" in s]
                
                if capture_ports:
                    node_name = "system (capture)"
                    saved_x, saved_y = self._preset_positions.get(node_name, (x, y))
                    node = self.model.add_node(node_name, saved_x, saved_y)
                    # Sort ports naturally before adding
                    import re
                    def natural_sort_key(item):
                        text = item[0]  # Sort by port_short
                        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
                    for port_short, port_full in sorted(capture_ports, key=natural_sort_key):
                        node.outputs.append(PortModel(port_short, port_full, True))
                    y += 150
                
                if playback_ports:
                    node_name = "system (playback)"
                    saved_x, saved_y = self._preset_positions.get(node_name, (x, y))
                    node = self.model.add_node(node_name, saved_x, saved_y)
                    # Sort ports naturally before adding
                    import re
                    def natural_sort_key(item):
                        text = item[0]  # Sort by port_short
                        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
                    for port_short, port_full in sorted(playback_ports, key=natural_sort_key):
                        node.inputs.append(PortModel(port_short, port_full, False))
                    y += 150
            
            elif client_name.startswith("a2j"):
                # Split a2j clients into capture (sources) and playback (sinks)
                capture_ports = [(s, f) for s, f, is_out in ports if is_out]
                playback_ports = [(s, f) for s, f, is_out in ports if not is_out]
                
                if capture_ports:
                    node_name = f"{client_name} (capture)"
                    saved_x, saved_y = self._preset_positions.get(node_name, (x, y))
                    node = self.model.add_node(node_name, saved_x, saved_y)
                    # Sort ports naturally before adding
                    import re
                    def natural_sort_key(item):
                        text = item[0]  # Sort by port_short
                        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
                    for port_short, port_full in sorted(capture_ports, key=natural_sort_key):
                        node.outputs.append(PortModel(port_short, port_full, True))
                    y += 150
                
                if playback_ports:
                    node_name = f"{client_name} (playback)"
                    saved_x, saved_y = self._preset_positions.get(node_name, (x, y))
                    node = self.model.add_node(node_name, saved_x, saved_y)
                    # Sort ports naturally before adding
                    import re
                    def natural_sort_key(item):
                        text = item[0]  # Sort by port_short
                        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
                    for port_short, port_full in sorted(playback_ports, key=natural_sort_key):
                        node.inputs.append(PortModel(port_short, port_full, False))
                    y += 150
            
            else:
                # Regular client - keep all ports together
                saved_x, saved_y = self._preset_positions.get(client_name, (x, y))
                node = self.model.add_node(client_name, saved_x, saved_y)
                # Sort ports naturally before adding
                import re
                def natural_sort_key(item):
                    text = item[0]  # Sort by port_short
                    return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
                for port_short, port_full, is_output in sorted(ports, key=natural_sort_key):
                    if is_output:
                        node.outputs.append(PortModel(port_short, port_full, True))
                    else:
                        node.inputs.append(PortModel(port_short, port_full, False))
                
                x += 200
                if x > 800:
                    x = 50
                    y += 150
        
        # Add connections - deduplicate to prevent double-drawing
        # jack_lsp -c shows connections from both output and input perspective
        # We only need to add each connection once
        added_connections = set()
        for out_port, in_ports_list in connections.items():
            # Check if out_port is actually an output (if not, skip - will be added from output side)
            if out_port not in output_ports_set:
                continue
            
            if isinstance(in_ports_list, list):
                for in_port in in_ports_list:
                    conn_key = (out_port, in_port)
                    if conn_key not in added_connections:
                        self.model.add_connection(out_port, in_port)
                        added_connections.add(conn_key)
            elif isinstance(in_ports_list, str):
                conn_key = (out_port, in_ports_list)
                if conn_key not in added_connections:
                    self.model.add_connection(out_port, in_ports_list)
                    added_connections.add(conn_key)
        
        # Clear preset positions after use
        self._preset_positions = {}
        
        # End batch - trigger rebuild
        self.model.end_batch()
    
    def _get_preset_path(self, name: str) -> Path:
        """Get preset path for current host."""
        if not self.current_node_host:
            return self.presets_dir / f"{name}.json"
        # Host-specific presets
        host_safe = self.current_node_host.replace(':', '_').replace('/', '_')
        return self.presets_dir / f"{host_safe}_{name}.json"
    
    def _save_preset(self):
        """Save current node positions and connections as a preset."""
        if not self.current_node_host:
            QMessageBox.warning(self, "No Host", "No remote host selected")
            return
        
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name:
            data = {
                "name": name,
                "host": self.current_node_host,
                "connections": {c.output_port: [c.input_port] for c in self.model.connections},
                "positions": {n.name: (n.x, n.y) for n in self.model.nodes.values()}
            }
            
            path = self._get_preset_path(name)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self._refresh_preset_list()
            QMessageBox.information(self, "Success", f"Preset '{name}' saved!")
    
    async def _load_preset_async(self):
        """Load preset asynchronously."""
        name = self.preset_combo.currentText()
        if not name:
            return
        
        path = self._get_preset_path(name)
        if not path.exists():
            return
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Store positions to be applied during next refresh
        self._preset_positions = data.get("positions", {})
        
        # Apply connections via SSH
        from skeleton_app.remote import SSHExecutor
        executor = SSHExecutor()
        
        for out_port, in_ports in data.get("connections", {}).items():
            for in_port in in_ports:
                try:
                    await executor.execute(
                        self.current_node_host,
                        f"jack_connect '{out_port}' '{in_port}'"
                    )
                except Exception as e:
                    logger.warning(f"Failed to connect {out_port} -> {in_port}: {e}")
        
        # Refresh to show updated state with positions
        await self._update_canvas()
        
        QMessageBox.information(self, "Success", f"Preset '{name}' loaded!")
    
    def _load_preset(self):
        """Load preset (sync wrapper)."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._load_preset_async())
            loop.close()
        except Exception as e:
            logger.error(f"Error loading preset: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load preset: {e}")
    
    def _refresh_preset_list(self):
        """Refresh preset list for current host."""
        current = self.preset_combo.currentText()
        self.preset_combo.clear()
        
        if not self.current_node_host:
            return
        
        # Find all presets for this host
        host_safe = self.current_node_host.replace(':', '_').replace('/', '_')
        prefix = f"{host_safe}_"
        
        presets = []
        for p in self.presets_dir.glob(f"{prefix}*.json"):
            # Remove host prefix and .json suffix
            name = p.stem[len(prefix):]
            presets.append(name)
        
        presets.sort()
        self.preset_combo.addItems(presets)
        
        idx = self.preset_combo.findText(current)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
    
    async def remote_connect_ports(self, output_port: str, input_port: str):
        """Create a connection on the remote host."""
        if not self.current_node_host:
            logger.error("No remote host configured")
            return
        
        from skeleton_app.remote import SSHExecutor
        executor = SSHExecutor()
        
        try:
            exit_code, stdout, stderr = await executor.execute(
                self.current_node_host,
                f"jack_connect '{output_port}' '{input_port}'"
            )
            
            if exit_code == 0:
                logger.info(f"Connected {output_port} -> {input_port} on {self.current_node_host}")
                # Refresh to show new connection
                await self._update_canvas()
            else:
                logger.error(f"Failed to connect: {stderr}")
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
    
    async def remote_disconnect_ports(self, output_port: str, input_port: str):
        """Remove a connection on the remote host."""
        if not self.current_node_host:
            logger.error("No remote host configured")
            return
        
        from skeleton_app.remote import SSHExecutor
        executor = SSHExecutor()
        
        try:
            exit_code, stdout, stderr = await executor.execute(
                self.current_node_host,
                f"jack_disconnect '{output_port}' '{input_port}'"
            )
            
            if exit_code == 0:
                logger.info(f"Disconnected {output_port} -/- {input_port} on {self.current_node_host}")
                # Refresh to show removed connection
                await self._update_canvas()
            else:
                logger.error(f"Failed to disconnect: {stderr}")
        except Exception as e:
            logger.error(f"SSH disconnection failed: {e}")


class RemoteGraphCanvas(GraphCanvas):
    """GraphCanvas subclass that handles remote JACK operations."""
    
    def __init__(self, model: GraphModel, remote_parent=None):
        super().__init__(model)
        self.remote_parent = remote_parent
    
    def _create_jack_connection(self, output_port: str, input_port: str):
        """Create a JACK connection on remote host."""
        if self.remote_parent:
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self.remote_parent.remote_connect_ports(output_port, input_port)
                )
                loop.close()
            except Exception as e:
                logger.error(f"Failed to create remote connection: {e}")
    
    def rebuild_view(self):
        """Rebuild all graphics items from model - use RemoteConnectionGraphicsItem."""
        from skeleton_app.gui.widgets.node_canvas_v3 import NodeGraphicsItem
        
        # Clear existing items
        for item in self.connection_items:
            self.scene.removeItem(item)
        for item in self.node_items.values():
            self.scene.removeItem(item)
        
        self.node_items.clear()
        self.connection_items.clear()
        
        # Create node items
        for node_model in self.model.nodes.values():
            item = NodeGraphicsItem(node_model, self.model)
            self.scene.addItem(item)
            self.node_items[node_model.name] = item
        
        # Create connection items (use RemoteConnectionGraphicsItem)
        for conn in self.model.connections:
            item = RemoteConnectionGraphicsItem(conn, self.model, self.node_items)
            self.scene.addItem(item)
            self.connection_items.append(item)
        
        # Update connection paths
        for item in self.connection_items:
            item.update_path()



# Need to override ConnectionGraphicsItem to use remote disconnect
from skeleton_app.gui.widgets.node_canvas_v3 import ConnectionGraphicsItem
from PySide6.QtCore import Qt

class RemoteConnectionGraphicsItem(ConnectionGraphicsItem):
    """Connection item that handles remote disconnections."""
    
    def mousePressEvent(self, event):
        """Right-click to delete connection on remote host."""
        if event.button() == Qt.RightButton:
            # Get parent widget to access remote operations
            if self.scene() and self.scene().views():
                view = self.scene().views()[0]
                if hasattr(view, 'remote_parent') and view.remote_parent:
                    import asyncio
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(
                            view.remote_parent.remote_disconnect_ports(
                                self.conn.output_port,
                                self.conn.input_port
                            )
                        )
                        loop.close()
                    except Exception as e:
                        logger.error(f"Failed to disconnect: {e}")
            event.accept()
        else:
            super().mousePressEvent(event)
