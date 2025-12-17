"""
Working node canvas - based on proven reference implementation.
"""

import json
import logging
from typing import Optional, Dict, List
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsEllipseItem, QGraphicsPathItem, QPushButton, QComboBox, QLabel,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QBrush, QFont

from skeleton_app.audio.jack_client import JackClientManager

logger = logging.getLogger(__name__)


class Socket(QGraphicsItem):
    """Port connection point on a node."""
    
    def __init__(self, parent, port_name: str, full_name: str, is_input: bool):
        super().__init__(parent)
        self.port_name = port_name
        self.full_name = full_name
        self.is_input = is_input
        self.edges = []
        self.setAcceptHoverEvents(True)
    
    def boundingRect(self):
        return QRectF(-6, -6, 12, 12)
    
    def paint(self, painter, option, widget):
        color = QColor("#3498db") if self.is_input else QColor("#2ecc71")
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.boundingRect())


class Edge(QGraphicsPathItem):
    """Connection line between two sockets."""
    
    def __init__(self, start_socket: Socket, end_socket: Socket):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket
        self.setPen(QPen(QColor("#f39c12"), 2))
        self.setZValue(-1)
        
        # Register with sockets
        start_socket.edges.append(self)
        end_socket.edges.append(self)
        
        self.update_path()
    
    def update_path(self):
        path = QPainterPath()
        start_pos = self.start_socket.scenePos()
        end_pos = self.end_socket.scenePos()
        path.moveTo(start_pos)
        
        # Bezier curve
        dist = abs(end_pos.x() - start_pos.x()) * 0.5
        path.cubicTo(
            start_pos.x() + dist, start_pos.y(),
            end_pos.x() - dist, end_pos.y(),
            end_pos.x(), end_pos.y()
        )
        self.setPath(path)


class Node(QGraphicsItem):
    """JACK client node with input/output sockets."""
    
    def __init__(self, client_name: str, x: float, y: float):
        super().__init__()
        self.client_name = client_name
        self.setPos(x, y)
        self.width, self.height = 150, 100
        
        # EXACT flags from working reference
        self.setFlags(
            QGraphicsItem.ItemIsMovable | 
            QGraphicsItem.ItemIsSelectable | 
            QGraphicsItem.ItemSendsScenePositionChanges
        )
        
        self.input_sockets: List[Socket] = []
        self.output_sockets: List[Socket] = []
    
    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)
    
    def paint(self, painter, option, widget):
        painter.setBrush(QColor("#2c3e50"))
        painter.setPen(QPen(QColor("#34495e"), 2))
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        # Title
        painter.setPen(QColor("#ecf0f1"))
        font = QFont("Sans", 10, QFont.Bold)
        painter.setFont(font)
        painter.drawText(10, 20, self.client_name)
    
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for socket in self.input_sockets + self.output_sockets:
                for edge in socket.edges:
                    edge.update_path()
        return super().itemChange(change, value)
    
    def add_input_socket(self, port_name: str, full_name: str) -> Socket:
        socket = Socket(self, port_name, full_name, is_input=True)
        y_offset = 35 + len(self.input_sockets) * 20
        socket.setPos(0, y_offset)
        self.input_sockets.append(socket)
        self._resize()
        return socket
    
    def add_output_socket(self, port_name: str, full_name: str) -> Socket:
        socket = Socket(self, port_name, full_name, is_input=False)
        y_offset = 35 + len(self.output_sockets) * 20
        socket.setPos(self.width, y_offset)
        self.output_sockets.append(socket)
        self._resize()
        return socket
    
    def _resize(self):
        max_sockets = max(len(self.input_sockets), len(self.output_sockets), 1)
        self.height = max(100, 35 + max_sockets * 20 + 10)
        
        # Reposition output sockets
        for i, socket in enumerate(self.output_sockets):
            socket.setPos(self.width, 35 + i * 20)


class NodeCanvas(QGraphicsView):
    """Graphics view for node graph."""
    
    connection_requested = Signal(str, str)
    disconnection_requested = Signal(str, str)
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        
        # Auto-layout
        self._next_x = 50
        self._next_y = 50
    
    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)
    
    def add_node(self, client_name: str, x: Optional[float] = None, y: Optional[float] = None) -> Node:
        if client_name in self.nodes:
            return self.nodes[client_name]
        
        if x is None or y is None:
            x, y = self._next_x, self._next_y
            self._next_x += 200
            if self._next_x > 800:
                self._next_x = 50
                self._next_y += 150
        
        node = Node(client_name, x, y)
        self.scene.addItem(node)
        self.nodes[client_name] = node
        return node
    
    def add_connection(self, output_port: str, input_port: str):
        out_socket = self._find_socket(output_port, is_output=True)
        in_socket = self._find_socket(input_port, is_output=False)
        
        if out_socket and in_socket:
            # Check if already connected
            for edge in self.edges:
                if edge.start_socket == out_socket and edge.end_socket == in_socket:
                    return
            
            edge = Edge(out_socket, in_socket)
            self.scene.addItem(edge)
            self.edges.append(edge)
    
    def remove_connection(self, output_port: str, input_port: str):
        out_socket = self._find_socket(output_port, is_output=True)
        in_socket = self._find_socket(input_port, is_output=False)
        
        if out_socket and in_socket:
            for edge in self.edges[:]:
                if edge.start_socket == out_socket and edge.end_socket == in_socket:
                    out_socket.edges.remove(edge)
                    in_socket.edges.remove(edge)
                    self.scene.removeItem(edge)
                    self.edges.remove(edge)
                    break
    
    def _find_socket(self, port_name: str, is_output: bool) -> Optional[Socket]:
        if ':' not in port_name:
            return None
        
        client_name = port_name.split(':')[0]
        port_short = ':'.join(port_name.split(':')[1:])
        
        node = self.nodes.get(client_name)
        if not node:
            return None
        
        sockets = node.output_sockets if is_output else node.input_sockets
        for socket in sockets:
            if socket.port_name == port_short:
                return socket
        return None
    
    def clear_all(self):
        for edge in self.edges[:]:
            self.scene.removeItem(edge)
        self.edges.clear()
        
        for node in self.nodes.values():
            self.scene.removeItem(node)
        self.nodes.clear()
        
        self._next_x = 50
        self._next_y = 50
    
    def get_node_positions(self) -> Dict[str, tuple]:
        return {name: (node.pos().x(), node.pos().y()) for name, node in self.nodes.items()}


class NodeCanvasWidget(QWidget):
    """Widget containing node canvas with controls."""
    
    def __init__(self, jack_manager: JackClientManager, parent=None):
        super().__init__(parent)
        self.jack_manager = jack_manager
        self.presets_dir = Path.home() / ".config" / "skeleton-app" / "jack-presets"
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        
        layout = QVBoxLayout(self)
        
        # Controls
        controls = QHBoxLayout()
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._refresh_canvas)
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
        self.canvas = NodeCanvas()
        self.canvas.connection_requested.connect(self._on_connect)
        self.canvas.disconnection_requested.connect(self._on_disconnect)
        layout.addWidget(self.canvas)
        
        # Auto-refresh timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_canvas)
        self._timer.start(2000)
        
        self._refresh_canvas()
        self._refresh_preset_list()
    
    def _refresh_canvas(self):
        try:
            # Get all ports
            all_ports = self.jack_manager.get_ports(is_audio=True)
            output_ports = set(self.jack_manager.get_ports(is_output=True, is_audio=True))
            connections = self.jack_manager.get_all_connections()
            
            # Group ports by client
            clients = {}
            for port_name in all_ports:
                if ':' not in port_name:
                    continue
                client_name = port_name.split(':')[0]
                port_short = ':'.join(port_name.split(':')[1:])
                if client_name not in clients:
                    clients[client_name] = []
                clients[client_name].append((port_short, port_name))
            
            # Clear and rebuild
            self.canvas.clear_all()
            
            # Create nodes
            for client_name, ports in clients.items():
                if client_name == "system":
                    # Split system into capture and playback
                    capture_ports = [(short, full) for short, full in ports if "capture" in short]
                    playback_ports = [(short, full) for short, full in ports if "playback" in short]
                    
                    if capture_ports:
                        node = self.canvas.add_node("system (capture)")
                        for port_short, port_full in capture_ports:
                            node.add_output_socket(port_short, port_full)
                    
                    if playback_ports:
                        node = self.canvas.add_node("system (playback)")
                        for port_short, port_full in playback_ports:
                            node.add_input_socket(port_short, port_full)
                else:
                    node = self.canvas.add_node(client_name)
                    for port_short, port_full in ports:
                        if port_full in output_ports:
                            node.add_output_socket(port_short, port_full)
                        else:
                            node.add_input_socket(port_short, port_full)
            
            # Create connections
            for out_port, in_ports in connections.items():
                for in_port in in_ports:
                    self.canvas.add_connection(out_port, in_port)
        
        except Exception as e:
            logger.error(f"Error refreshing canvas: {e}", exc_info=True)
    
    def _on_connect(self, output_port: str, input_port: str):
        try:
            self.jack_manager.connect_ports(output_port, input_port)
            self._refresh_canvas()
        except Exception as e:
            QMessageBox.warning(self, "Connection Failed", str(e))
    
    def _on_disconnect(self, output_port: str, input_port: str):
        try:
            self.jack_manager.disconnect_ports(output_port, input_port)
            self._refresh_canvas()
        except Exception as e:
            QMessageBox.warning(self, "Disconnection Failed", str(e))
    
    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if ok and name:
            connections = self.jack_manager.get_all_connections()
            positions = self.canvas.get_node_positions()
            
            data = {
                "name": name,
                "connections": connections,
                "positions": positions
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
            QMessageBox.warning(self, "Error", f"Preset '{name}' not found!")
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
        
        self._refresh_canvas()
    
    def _refresh_preset_list(self):
        current = self.preset_combo.currentText()
        self.preset_combo.clear()
        
        presets = [p.stem for p in self.presets_dir.glob("*.json")]
        presets.sort()
        self.preset_combo.addItems(presets)
        
        idx = self.preset_combo.findText(current)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
