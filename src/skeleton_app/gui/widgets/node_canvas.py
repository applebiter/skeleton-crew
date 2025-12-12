"""
Node canvas widget - visual graph representation of JACK connections.

Similar to Carla's patchbay canvas but extensible for custom node types.
"""

from typing import Optional, Dict, List, Set, Tuple
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QPushButton, QComboBox, QLabel, QToolBar
)
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal, QLineF
from PySide6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPainterPath,
    QLinearGradient, QFont
)

from skeleton_app.audio.jack_client import JackClientManager


class PortType(Enum):
    """Port type enumeration."""
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    MIDI_INPUT = "midi_input"
    MIDI_OUTPUT = "midi_output"


class PortItem(QGraphicsEllipseItem):
    """Visual representation of a port."""
    
    def __init__(self, port_name: str, port_type: PortType, parent=None):
        super().__init__(-6, -6, 12, 12, parent)
        self.port_name = port_name
        self.port_type = port_type
        
        # Style based on type
        if port_type == PortType.AUDIO_OUTPUT:
            self.setBrush(QBrush(QColor(60, 180, 60)))  # Green
        elif port_type == PortType.AUDIO_INPUT:
            self.setBrush(QBrush(QColor(60, 60, 180)))  # Blue
        
        self.setPen(QPen(QColor(0, 0, 0), 2))
        self.setAcceptHoverEvents(True)
        
        # Connection tracking
        self.connections: List['ConnectionItem'] = []
    
    def hoverEnterEvent(self, event):
        """Highlight on hover."""
        self.setBrush(QBrush(QColor(255, 255, 0)))  # Yellow
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Restore color."""
        if self.port_type == PortType.AUDIO_OUTPUT:
            self.setBrush(QBrush(QColor(60, 180, 60)))
        elif self.port_type == PortType.AUDIO_INPUT:
            self.setBrush(QBrush(QColor(60, 60, 180)))
        super().hoverLeaveEvent(event)


class NodeItem(QGraphicsRectItem):
    """Visual representation of a JACK client node."""
    
    def __init__(self, client_name: str, x: float = 0, y: float = 0):
        super().__init__(0, 0, 150, 100)
        self.client_name = client_name
        self.setPos(x, y)
        
        # Style
        self.setBrush(QBrush(QColor(50, 50, 50)))
        self.setPen(QPen(QColor(200, 200, 200), 2))
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        
        # Title
        self.title = QGraphicsTextItem(client_name, self)
        self.title.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont("Sans", 10, QFont.Bold)
        self.title.setFont(font)
        self.title.setPos(10, 5)
        
        # Ports
        self.input_ports: List[PortItem] = []
        self.output_ports: List[PortItem] = []
    
    def add_input_port(self, port_name: str, port_type: PortType = PortType.AUDIO_INPUT):
        """Add an input port to the left side."""
        port = PortItem(port_name, port_type, self)
        y_offset = 30 + len(self.input_ports) * 20
        port.setPos(0, y_offset)
        self.input_ports.append(port)
        self._resize_to_fit_ports()
        return port
    
    def add_output_port(self, port_name: str, port_type: PortType = PortType.AUDIO_OUTPUT):
        """Add an output port to the right side."""
        port = PortItem(port_name, port_type, self)
        y_offset = 30 + len(self.output_ports) * 20
        port.setPos(self.rect().width(), y_offset)
        self.output_ports.append(port)
        self._resize_to_fit_ports()
        return port
    
    def _resize_to_fit_ports(self):
        """Resize node to fit all ports."""
        max_ports = max(len(self.input_ports), len(self.output_ports), 1)
        new_height = max(100, 30 + max_ports * 20 + 10)
        self.setRect(0, 0, 150, new_height)
        
        # Reposition output ports to right edge
        for i, port in enumerate(self.output_ports):
            port.setPos(self.rect().width(), 30 + i * 20)


class ConnectionItem(QGraphicsLineItem):
    """Visual representation of a connection between ports."""
    
    def __init__(self, output_port: PortItem, input_port: PortItem):
        super().__init__()
        self.output_port = output_port
        self.input_port = input_port
        
        # Style
        self.setPen(QPen(QColor(200, 200, 100), 2))
        self.setZValue(-1)  # Behind nodes
        
        # Track in ports
        output_port.connections.append(self)
        input_port.connections.append(self)
        
        self.update_position()
    
    def update_position(self):
        """Update line position based on port positions."""
        start = self.output_port.sceneBoundingRect().center()
        end = self.input_port.sceneBoundingRect().center()
        self.setLine(QLineF(start, end))


class NodeCanvas(QGraphicsView):
    """
    Canvas for displaying nodes and connections.
    
    Similar to Carla's patchbay but with support for custom node types.
    """
    
    # Signals
    connection_requested = Signal(str, str)  # output_port, input_port
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Style
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setSceneRect(-2000, -2000, 4000, 4000)
        
        # Enable panning
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        
        # Node tracking
        self.nodes: Dict[str, NodeItem] = {}  # client_name -> NodeItem
        self.connections: List[ConnectionItem] = []
        
        # Auto-layout tracking
        self._next_node_x = 50
        self._next_node_y = 50
    
    def add_node(self, client_name: str, x: Optional[float] = None, y: Optional[float] = None) -> NodeItem:
        """Add a node to the canvas."""
        if client_name in self.nodes:
            return self.nodes[client_name]
        
        # Use provided position or auto-layout
        if x is None or y is None:
            x = self._next_node_x
            y = self._next_node_y
            
            # Auto-layout in grid
            self._next_node_x += 200
            if self._next_node_x > 800:
                self._next_node_x = 50
                self._next_node_y += 150
        
        node = NodeItem(client_name, x, y)
        self.scene.addItem(node)
        self.nodes[client_name] = node
        return node
    
    def add_connection(self, output_port_name: str, input_port_name: str):
        """Add a visual connection between ports."""
        # Find ports
        output_port = self._find_port(output_port_name, is_output=True)
        input_port = self._find_port(input_port_name, is_output=False)
        
        if output_port and input_port:
            connection = ConnectionItem(output_port, input_port)
            self.scene.addItem(connection)
            self.connections.append(connection)
    
    def _find_port(self, port_name: str, is_output: bool) -> Optional[PortItem]:
        """Find a port by its full name."""
        if ':' not in port_name:
            return None
        
        client_name = port_name.split(':')[0]
        port_short_name = port_name.split(':')[1]
        
        node = self.nodes.get(client_name)
        if not node:
            return None
        
        ports = node.output_ports if is_output else node.input_ports
        for port in ports:
            if port_short_name in port.port_name:
                return port
        
        return None
    
    def clear_all(self):
        """Clear all nodes and connections."""
        self.scene.clear()
        self.nodes.clear()
        self.connections.clear()
        self._next_node_x = 50
        self._next_node_y = 50
    
    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1 / zoom_factor, 1 / zoom_factor)


class NodeCanvasWidget(QWidget):
    """
    Node canvas widget with toolbar.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jack_manager: Optional[JackClientManager] = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup UI."""
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        toolbar_label = QLabel("Node Canvas:")
        toolbar_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        toolbar.addWidget(toolbar_label)
        
        toolbar.addStretch()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_canvas)
        toolbar.addWidget(self.refresh_button)
        
        self.auto_arrange_button = QPushButton("Auto-Arrange")
        self.auto_arrange_button.clicked.connect(self._auto_arrange)
        toolbar.addWidget(self.auto_arrange_button)
        
        self.zoom_in_button = QPushButton("Zoom In")
        self.zoom_in_button.clicked.connect(lambda: self.canvas.scale(1.2, 1.2))
        toolbar.addWidget(self.zoom_in_button)
        
        self.zoom_out_button = QPushButton("Zoom Out")
        self.zoom_out_button.clicked.connect(lambda: self.canvas.scale(1/1.2, 1/1.2))
        toolbar.addWidget(self.zoom_out_button)
        
        self.zoom_fit_button = QPushButton("Fit All")
        self.zoom_fit_button.clicked.connect(self._fit_all)
        toolbar.addWidget(self.zoom_fit_button)
        
        layout.addLayout(toolbar)
        
        # Canvas
        self.canvas = NodeCanvas(self)
        layout.addWidget(self.canvas)
    
    def set_jack_manager(self, jack_manager: Optional[JackClientManager]):
        """Set JACK manager and populate canvas."""
        self.jack_manager = jack_manager
        if jack_manager:
            self._refresh_canvas()
    
    def _refresh_canvas(self):
        """Refresh canvas from JACK state."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            return
        
        # Clear and rebuild
        self.canvas.clear_all()
        
        # Get all ports
        output_ports = self.jack_manager.get_ports(is_output=True, is_audio=True)
        input_ports = self.jack_manager.get_ports(is_input=True, is_audio=True)
        
        # Create nodes for each client
        clients = set()
        for port in output_ports + input_ports:
            client_name = port.split(':')[0]
            clients.add(client_name)
        
        for client_name in sorted(clients):
            node = self.canvas.add_node(client_name)
            
            # Add output ports
            for port in output_ports:
                if port.startswith(client_name + ':'):
                    port_name = port.split(':')[1]
                    node.add_output_port(port_name)
            
            # Add input ports
            for port in input_ports:
                if port.startswith(client_name + ':'):
                    port_name = port.split(':')[1]
                    node.add_input_port(port_name)
        
        # Add connections
        connections = self.jack_manager.get_all_connections()
        for output_port, input_ports in connections.items():
            for input_port in input_ports:
                self.canvas.add_connection(output_port, input_port)
    
    def _auto_arrange(self):
        """Auto-arrange nodes in a grid."""
        x, y = 50, 50
        for node in self.canvas.nodes.values():
            node.setPos(x, y)
            x += 200
            if x > 800:
                x = 50
                y += 150
    
    def _fit_all(self):
        """Fit all nodes in view."""
        self.canvas.fitInView(self.canvas.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
