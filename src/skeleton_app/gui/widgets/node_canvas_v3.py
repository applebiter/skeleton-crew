"""
Node canvas with strict Model-View separation.
Following 2025 best practices: Data structure separate from UI rendering.
"""

import json
import logging
from typing import Optional, Dict, List, Set, Tuple
from pathlib import Path
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QPushButton, QComboBox, QLabel,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal, QObject
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QBrush, QFont

from skeleton_app.audio.jack_client import JackClientManager

logger = logging.getLogger(__name__)


# ============================================================================
# PURE DATA MODEL (No Qt, No UI)
# ============================================================================

@dataclass
class PortModel:
    """Pure data: a port on a node."""
    name: str
    full_name: str
    is_output: bool

@dataclass
class NodeModel:
    """Pure data: a JACK client with ports."""
    name: str
    inputs: List[PortModel] = field(default_factory=list)
    outputs: List[PortModel] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0

@dataclass
class ConnectionModel:
    """Pure data: connection between two ports."""
    output_port: str  # full name
    input_port: str   # full name

class GraphModel(QObject):
    """Pure data model of the JACK graph. No rendering logic."""
    
    changed = Signal()  # Emitted when model changes
    
    def __init__(self):
        super().__init__()
        self.nodes: Dict[str, NodeModel] = {}
        self.connections: List[ConnectionModel] = []
    
    def add_node(self, name: str, x: float = 0, y: float = 0) -> NodeModel:
        if name not in self.nodes:
            self.nodes[name] = NodeModel(name=name, x=x, y=y)
            self.changed.emit()
        return self.nodes[name]
    
    def move_node(self, name: str, x: float, y: float):
        if name in self.nodes:
            self.nodes[name].x = x
            self.nodes[name].y = y
            self.changed.emit()
    
    def add_connection(self, output_port: str, input_port: str):
        conn = ConnectionModel(output_port, input_port)
        if conn not in self.connections:
            self.connections.append(conn)
            self.changed.emit()
    
    def clear(self):
        self.nodes.clear()
        self.connections.clear()
        self.changed.emit()


# ============================================================================
# VIEW LAYER (Qt Graphics Items - render the model)
# ============================================================================

class NodeGraphicsItem(QGraphicsItem):
    """Visual representation of a NodeModel. Pure rendering, no data."""
    
    def __init__(self, model: NodeModel, graph_model: GraphModel):
        super().__init__()
        self.model = model
        self.graph_model = graph_model
        
        # CRITICAL: Use exact flags from working test
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsScenePositionChanges
        )
        
        self.setPos(model.x, model.y)
        self.width = 150
        self.height = 100
    
    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)
    
    def paint(self, painter, option, widget):
        # Background
        painter.setBrush(QColor(50, 50, 50))
        painter.setPen(QPen(QColor(200, 200, 200), 2))
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        # Title
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Sans", 9, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(5, 5, self.width - 10, 20), Qt.AlignLeft, self.model.name)
        
        # Input ports (left side)
        y = 30
        painter.setFont(QFont("Sans", 8))
        for port in self.model.inputs:
            painter.setBrush(QColor(100, 100, 255))
            painter.drawEllipse(QPointF(0, y), 5, 5)
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(QRectF(12, y - 8, self.width - 24, 16), Qt.AlignLeft, port.name)
            y += 18
        
        # Output ports (right side)
        y = 30
        for port in self.model.outputs:
            painter.setBrush(QColor(100, 255, 100))
            painter.drawEllipse(QPointF(self.width, y), 5, 5)
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(QRectF(12, y - 8, self.width - 24, 16), Qt.AlignRight, port.name)
            y += 18
        
        # Adjust height based on ports
        max_ports = max(len(self.model.inputs), len(self.model.outputs), 1)
        self.height = max(100, 30 + max_ports * 18 + 10)
    
    def itemChange(self, change, value):
        # Update model when position changes - but DON'T emit changed signal during drag
        if change == QGraphicsItem.ItemPositionHasChanged:
            pos = value.toPointF() if hasattr(value, 'toPointF') else self.pos()
            # Update model silently (no signal emission)
            self.model.x = pos.x()
            self.model.y = pos.y()
            # Only update connections that are attached to this node
            for item in self.scene().items():
                if isinstance(item, ConnectionGraphicsItem):
                    if self.model.name in item.conn.output_port or self.model.name in item.conn.input_port:
                        item.update_path()
        return super().itemChange(change, value)
    
    def get_port_scene_pos(self, port_name: str, is_output: bool) -> QPointF:
        """Get scene position of a port."""
        ports = self.model.outputs if is_output else self.model.inputs
        for i, port in enumerate(ports):
            if port.name == port_name:
                y = 30 + i * 18
                x = self.width if is_output else 0
                return self.mapToScene(QPointF(x, y))
        return self.scenePos()


class ConnectionGraphicsItem(QGraphicsItem):
    """Visual representation of a ConnectionModel."""
    
    def __init__(self, conn: ConnectionModel, graph_model: GraphModel, node_items: Dict[str, NodeGraphicsItem]):
        super().__init__()
        self.conn = conn
        self.graph_model = graph_model
        self.node_items = node_items
        self.setZValue(-1)  # Behind nodes
        self.path = QPainterPath()
        self.update_path()
    
    def boundingRect(self):
        return self.path.boundingRect()
    
    def paint(self, painter, option, widget):
        painter.setPen(QPen(QColor(255, 200, 100), 2))
        painter.drawPath(self.path)
    
    def update_path(self):
        # Find start and end positions
        start_pos = self._get_port_pos(self.conn.output_port, is_output=True)
        end_pos = self._get_port_pos(self.conn.input_port, is_output=False)
        
        if start_pos and end_pos:
            self.path = QPainterPath()
            self.path.moveTo(start_pos)
            
            # Bezier curve
            dist = abs(end_pos.x() - start_pos.x()) * 0.5
            self.path.cubicTo(
                start_pos.x() + dist, start_pos.y(),
                end_pos.x() - dist, end_pos.y(),
                end_pos.x(), end_pos.y()
            )
            self.prepareGeometryChange()
    
    def _get_port_pos(self, full_port_name: str, is_output: bool) -> Optional[QPointF]:
        if ':' not in full_port_name:
            return None
        
        client_name = full_port_name.split(':')[0]
        port_name = ':'.join(full_port_name.split(':')[1:])
        
        # Handle system split
        if client_name == "system":
            if "capture" in port_name:
                client_name = "system (capture)"
            elif "playback" in port_name:
                client_name = "system (playback)"
        
        node_item = self.node_items.get(client_name)
        if node_item:
            return node_item.get_port_scene_pos(port_name, is_output)
        return None


class GraphCanvas(QGraphicsView):
    """View layer - renders the GraphModel."""
    
    def __init__(self, model: GraphModel):
        super().__init__()
        self.model = model
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        self.node_items: Dict[str, NodeGraphicsItem] = {}
        self.connection_items: List[ConnectionGraphicsItem] = []
        
        # Rebuild view when model changes
        self.model.changed.connect(self.rebuild_view)
    
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
    
    def rebuild_view(self):
        """Rebuild all graphics items from model."""
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
        
        # Create connection items
        for conn in self.model.connections:
            item = ConnectionGraphicsItem(conn, self.model, self.node_items)
            self.scene.addItem(item)
            self.connection_items.append(item)
        
        # Update connection paths
        for item in self.connection_items:
            item.update_path()


# ============================================================================
# CONTROLLER WIDGET
# ============================================================================

class NodeCanvasWidget(QWidget):
    """Controller - bridges JACK manager and GraphModel."""
    
    def __init__(self, jack_manager: JackClientManager, parent=None):
        super().__init__(parent)
        self.jack_manager = jack_manager
        self.presets_dir = Path.home() / ".config" / "skeleton-app" / "jack-presets"
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        
        # Model
        self.model = GraphModel()
        
        # View
        layout = QVBoxLayout(self)
        
        # Controls
        controls = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self.refresh_from_jack)
        controls.addWidget(btn_refresh)
        
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
        layout.addLayout(controls)
        
        # Canvas
        self.canvas = GraphCanvas(self.model)
        layout.addWidget(self.canvas)
        
        # Auto-refresh
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_from_jack)
        self._timer.start(2000)
        
        self.refresh_from_jack()
        self._refresh_preset_list()
    
    def refresh_from_jack(self):
        """Update model from JACK state."""
        try:
            # Get JACK data
            all_ports = self.jack_manager.get_ports(is_audio=True)
            output_ports = set(self.jack_manager.get_ports(is_output=True, is_audio=True))
            connections_dict = self.jack_manager.get_all_connections()
            
            # Clear model
            self.model.clear()
            
            # Group ports by client
            clients = {}
            for port_name in all_ports:
                if ':' not in port_name:
                    continue
                client_name = port_name.split(':')[0]
                port_short = ':'.join(port_name.split(':')[1:])
                if client_name not in clients:
                    clients[client_name] = []
                clients[client_name].append((port_short, port_name, port_name in output_ports))
            
            # Create nodes with auto-layout
            x, y = 50, 50
            for client_name, ports in clients.items():
                if client_name == "system":
                    # Split system
                    capture_ports = [(s, f) for s, f, _ in ports if "capture" in s]
                    playback_ports = [(s, f) for s, f, _ in ports if "playback" in s]
                    
                    if capture_ports:
                        node = self.model.add_node("system (capture)", x, y)
                        for port_short, port_full in capture_ports:
                            node.outputs.append(PortModel(port_short, port_full, True))
                        y += 150
                    
                    if playback_ports:
                        node = self.model.add_node("system (playback)", x, y)
                        for port_short, port_full in playback_ports:
                            node.inputs.append(PortModel(port_short, port_full, False))
                        y += 150
                else:
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
            
            # Add connections
            for out_port, in_ports in connections_dict.items():
                for in_port in in_ports:
                    self.model.add_connection(out_port, in_port)
        
        except Exception as e:
            logger.error(f"Error refreshing from JACK: {e}", exc_info=True)
    
    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name:
            data = {
                "name": name,
                "connections": {c.output_port: [c.input_port] for c in self.model.connections},
                "positions": {n.name: (n.x, n.y) for n in self.model.nodes.values()}
            }
            
            path = self.presets_dir / f"{name}.json"
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self._refresh_preset_list()
            QMessageBox.information(self, "Success", f"Preset '{name}' saved!")
    
    def _load_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return
        
        path = self.presets_dir / f"{name}.json"
        if not path.exists():
            return
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Apply connections
        for out_port, in_ports in data.get("connections", {}).items():
            for in_port in in_ports:
                try:
                    self.jack_manager.connect_ports(out_port, in_port)
                except:
                    pass
        
        self.refresh_from_jack()
    
    def _refresh_preset_list(self):
        current = self.preset_combo.currentText()
        self.preset_combo.clear()
        
        presets = [p.stem for p in self.presets_dir.glob("*.json")]
        presets.sort()
        self.preset_combo.addItems(presets)
        
        idx = self.preset_combo.findText(current)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
