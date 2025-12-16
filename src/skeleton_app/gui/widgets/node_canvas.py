"""
Node canvas widget - visual graph representation of JACK connections.

Similar to Carla's patchbay canvas but extensible for custom node types.
Supports saving/loading connection presets.
"""

import json
import logging
from typing import Optional, Dict, List, Set, Tuple
from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QPushButton, QComboBox, QLabel, QToolBar,
    QInputDialog, QMessageBox, QFileDialog, QSizePolicy
)
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal, QLineF, QSize, QPoint
from PySide6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPainterPath,
    QLinearGradient, QFont, QAction, QResizeEvent
)

from skeleton_app.audio.jack_client import JackClientManager

logger = logging.getLogger(__name__)


class PortType(Enum):
    """Port type enumeration."""
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    MIDI_INPUT = "midi_input"
    MIDI_OUTPUT = "midi_output"


class PortItem(QGraphicsEllipseItem):
    """Visual representation of a port (connection point)."""
    
    def __init__(self, port_name: str, port_type: PortType, parent: QGraphicsItem):
        super().__init__(-6, -6, 12, 12, parent)
        self.port_name = port_name
        self.port_type = port_type
        self.full_name = ""  # Set by parent node
        
        # Color by type
        if port_type == PortType.AUDIO_OUTPUT:
            self.setBrush(QBrush(QColor(60, 180, 60)))  # Green
        elif port_type == PortType.AUDIO_INPUT:
            self.setBrush(QBrush(QColor(60, 60, 180)))  # Blue
        elif port_type == PortType.MIDI_OUTPUT:
            self.setBrush(QBrush(QColor(180, 60, 180)))  # Magenta
        elif port_type == PortType.MIDI_INPUT:
            self.setBrush(QBrush(QColor(180, 180, 60)))  # Yellow
        
        self.setPen(QPen(QColor(0, 0, 0), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        
        # Connection tracking
        self.connections: List['ConnectionItem'] = []
        
        # Drag state for creating connections
        self._drag_line: Optional[QGraphicsLineItem] = None
    
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
        elif self.port_type == PortType.MIDI_OUTPUT:
            self.setBrush(QBrush(QColor(180, 60, 180)))
        elif self.port_type == PortType.MIDI_INPUT:
            self.setBrush(QBrush(QColor(180, 180, 60)))
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        """Start dragging connection."""
        if event.button() == Qt.LeftButton and self.port_type in (PortType.AUDIO_OUTPUT, PortType.MIDI_OUTPUT):
            # Start drag from output port
            start = self.sceneBoundingRect().center()
            self._drag_line = QGraphicsLineItem(QLineF(start, start))
            self._drag_line.setPen(QPen(QColor(255, 255, 100), 2, Qt.DashLine))
            self.scene().addItem(self._drag_line)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Update drag line."""
        if self._drag_line:
            start = self.sceneBoundingRect().center()
            end = event.scenePos()
            self._drag_line.setLine(QLineF(start, end))
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Complete connection."""
        if self._drag_line:
            # Find target port
            target_item = self.scene().itemAt(event.scenePos(), self.scene().views()[0].transform())
            if isinstance(target_item, PortItem):
                # Check if valid connection (output -> input, same type)
                if (self.port_type == PortType.AUDIO_OUTPUT and target_item.port_type == PortType.AUDIO_INPUT) or \
                   (self.port_type == PortType.MIDI_OUTPUT and target_item.port_type == PortType.MIDI_INPUT):
                    # Emit connection request
                    canvas = self.scene().views()[0]
                    if hasattr(canvas, 'connection_requested'):
                        canvas.connection_requested.emit(self.full_name, target_item.full_name)
            
            # Remove drag line
            self.scene().removeItem(self._drag_line)
            self._drag_line = None
        
        super().mouseReleaseEvent(event)


class NodeItem(QGraphicsRectItem):
    """Visual representation of a JACK client node."""
    
    def __init__(self, client_name: str, x: float = 0, y: float = 0):
        super().__init__(0, 0, 150, 100)
        self.client_name = client_name
        self.setPos(x, y)
        
        # Style
        self.setBrush(QBrush(QColor(50, 50, 50)))
        self.setPen(QPen(QColor(200, 200, 200), 2))
        # Make items movable and selectable
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
    
    def itemChange(self, change, value):
        """Handle item changes to update connections."""
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._update_connections()
        return super().itemChange(change, value)
    
    def add_input_port(self, port_name: str, port_type: PortType = PortType.AUDIO_INPUT) -> PortItem:
        """Add an input port to the left side."""
        port = PortItem(port_name, port_type, self)
        port.full_name = f"{self.client_name}:{port_name}"
        y_offset = 30 + len(self.input_ports) * 20
        port.setPos(0, y_offset)
        self.input_ports.append(port)
        self._resize_to_fit_ports()
        return port
    
    def add_output_port(self, port_name: str, port_type: PortType = PortType.AUDIO_OUTPUT) -> PortItem:
        """Add an output port to the right side."""
        port = PortItem(port_name, port_type, self)
        port.full_name = f"{self.client_name}:{port_name}"
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
    
    def _update_connections(self):
        """Update all connected lines."""
        for port in self.input_ports + self.output_ports:
            for connection in port.connections:
                connection.update_position()


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
    
    def mousePressEvent(self, event):
        """Handle disconnection on right-click."""
        if event.button() == Qt.RightButton:
            canvas = self.scene().views()[0]
            if hasattr(canvas, 'disconnection_requested'):
                canvas.disconnection_requested.emit(
                    self.output_port.full_name,
                    self.input_port.full_name
                )
        super().mousePressEvent(event)


class NodeCanvas(QGraphicsView):
    """
    Canvas for displaying nodes and connections.
    
    Similar to Carla's patchbay but with support for custom node types.
    """
    
    # Signals
    connection_requested = Signal(str, str)  # output_port, input_port
    disconnection_requested = Signal(str, str)  # output_port, input_port
    viewport_changed = Signal()  # Emitted when viewport moves/zooms
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Style
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)  # Essential for zoom
        
        # Start with no drag mode
        self.setDragMode(QGraphicsView.NoDrag)
        
        # Node tracking
        self.nodes: Dict[str, NodeItem] = {}  # client_name -> NodeItem
        self.connections: List[ConnectionItem] = []
        
        # Auto-layout tracking
        self._next_node_x = 50
        self._next_node_y = 50
        
        # Minimap
        self.minimap: Optional['MiniMapView'] = None
    
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
            # Check if connection already exists
            for conn in self.connections:
                if conn.output_port == output_port and conn.input_port == input_port:
                    return  # Already connected
            
            connection = ConnectionItem(output_port, input_port)
            self.scene.addItem(connection)
            self.connections.append(connection)
    
    def remove_connection(self, output_port_name: str, input_port_name: str):
        """Remove a visual connection."""
        output_port = self._find_port(output_port_name, is_output=True)
        input_port = self._find_port(input_port_name, is_output=False)
        
        if output_port and input_port:
            for conn in self.connections[:]:
                if conn.output_port == output_port and conn.input_port == input_port:
                    output_port.connections.remove(conn)
                    input_port.connections.remove(conn)
                    self.scene.removeItem(conn)
                    self.connections.remove(conn)
                    break
    
    def _find_port(self, port_name: str, is_output: bool) -> Optional[PortItem]:
        """Find a port by its full name."""
        if ':' not in port_name:
            return None
        
        client_name = port_name.split(':')[0]
        port_short_name = ':'.join(port_name.split(':')[1:])
        
        node = self.nodes.get(client_name)
        if not node:
            return None
        
        ports = node.output_ports if is_output else node.input_ports
        for port in ports:
            if port.port_name == port_short_name:
                return port
        
        return None
    
    def clear_all(self):
        """Clear all nodes and connections."""
        # Remove nodes and connections but keep other items
        for conn in self.connections[:]:
            self.scene.removeItem(conn)
        self.connections.clear()
        
        for node in self.nodes.values():
            self.scene.removeItem(node)
        self.nodes.clear()
        
        self._next_node_x = 50
        self._next_node_y = 50
    
    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1 / zoom_factor, 1 / zoom_factor)
        self.viewport_changed.emit()
    
    def mousePressEvent(self, event):
        """Enable canvas panning with middle mouse or left-click on background."""
        item_at_pos = self.itemAt(event.pos())
        
        # Middle mouse always pans
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            super().mousePressEvent(event)
        # Left mouse on background also pans
        elif event.button() == Qt.LeftButton and not item_at_pos:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            # Create a fake middle mouse event to trigger panning
            super().mousePressEvent(event)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Reset drag mode when middle mouse is released."""
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.NoDrag)
    
    def scrollContentsBy(self, dx: int, dy: int):
        """Override to emit viewport changed signal."""
        super().scrollContentsBy(dx, dy)
        self.viewport_changed.emit()
    
    def get_node_positions(self) -> Dict[str, Tuple[float, float]]:
        """Get positions of all nodes."""
        return {name: (node.pos().x(), node.pos().y()) for name, node in self.nodes.items()}
    
    def set_node_positions(self, positions: Dict[str, Tuple[float, float]]):
        """Set positions of nodes."""
        for name, (x, y) in positions.items():
            if name in self.nodes:
                self.nodes[name].setPos(x, y)


class MiniMapView(QGraphicsView):
    """
    Minimap overlay showing entire canvas with viewport rectangle.
    """
    
    viewport_move_requested = Signal(QPointF)  # Request to center main view at this point
    
    def __init__(self, main_view: NodeCanvas, parent: Optional[QWidget] = None):
        super().__init__(main_view.scene, parent)
        self.main_view = main_view
        
        # Style
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(20, 20, 20, 180)))  # Semi-transparent
        self.setFrameStyle(2)  # Box frame
        
        # Fixed size
        self.setFixedSize(200, 150)
        
        # Disable interaction (we'll handle it manually)
        self.setInteractive(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Viewport rectangle
        self.viewport_rect = QGraphicsRectItem()
        self.viewport_rect.setPen(QPen(QColor(255, 100, 100), 2))
        self.viewport_rect.setBrush(QBrush(QColor(255, 100, 100, 30)))
        self.viewport_rect.setZValue(1000)  # On top
        self.scene().addItem(self.viewport_rect)
        
        # Dragging state
        self._dragging = False
        self._drag_start_pos = QPointF()
        
        # Initial fit
        self.refit_minimap()
    
    def update_viewport_rect(self):
        """Update the viewport rectangle to match main view."""
        try:
            # Get the visible area in the main view's scene coordinates
            # This accounts for zoom and pan transformations
            view_rect = self.main_view.viewport().rect()
            top_left = self.main_view.mapToScene(view_rect.topLeft())
            top_right = self.main_view.mapToScene(view_rect.topRight())
            bottom_left = self.main_view.mapToScene(view_rect.bottomLeft())
            bottom_right = self.main_view.mapToScene(view_rect.bottomRight())
            
            # Calculate bounding rect of these points
            min_x = min(top_left.x(), top_right.x(), bottom_left.x(), bottom_right.x())
            max_x = max(top_left.x(), top_right.x(), bottom_left.x(), bottom_right.x())
            min_y = min(top_left.y(), top_right.y(), bottom_left.y(), bottom_right.y())
            max_y = max(top_left.y(), top_right.y(), bottom_left.y(), bottom_right.y())
            
            visible_rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
            self.viewport_rect.setRect(visible_rect)
        except RuntimeError:
            # Object may have been deleted
            pass
    
    def refit_minimap(self):
        """Refit minimap to show entire scene. Call this when nodes are added/removed."""
        if self.main_view.nodes:
            # Fit to actual content bounds with some padding
            content_rect = self.scene().itemsBoundingRect()
            # Add 10% padding around content
            padding = max(content_rect.width(), content_rect.height()) * 0.1
            padded_rect = content_rect.adjusted(-padding, -padding, padding, padding)
            self.fitInView(padded_rect, Qt.KeepAspectRatio)
        else:
            # No nodes yet - use default scene rect
            self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
    
    def mousePressEvent(self, event):
        """Start dragging viewport."""
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_pos = self.mapToScene(event.pos())
            # Center main view on clicked point
            self.viewport_move_requested.emit(self._drag_start_pos)
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Drag viewport rectangle."""
        if self._dragging:
            scene_pos = self.mapToScene(event.pos())
            self.viewport_move_requested.emit(scene_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Stop dragging."""
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class NodeCanvasWidget(QWidget):
    """
    Node canvas widget with toolbar and preset management.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.jack_manager: Optional[JackClientManager] = None
        self.presets_dir = Path.home() / ".config" / "skeleton-app" / "jack-presets"
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        
        self._setup_ui()
        
        # Auto-refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start(2000)  # Refresh every 2 seconds
    
    def _setup_ui(self):
        """Setup UI."""
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        toolbar_label = QLabel("Node Canvas:")
        toolbar_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        toolbar.addWidget(toolbar_label)
        
        toolbar.addStretch()
        
        # Preset controls
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(150)
        self.preset_combo.setPlaceholderText("Select preset...")
        self._refresh_preset_list()
        toolbar.addWidget(QLabel("Preset:"))
        toolbar.addWidget(self.preset_combo)
        
        self.save_preset_button = QPushButton("💾 Save")
        self.save_preset_button.clicked.connect(self._save_preset)
        self.save_preset_button.setToolTip("Save current connections as preset")
        toolbar.addWidget(self.save_preset_button)
        
        self.load_preset_button = QPushButton("📂 Load")
        self.load_preset_button.clicked.connect(self._load_preset)
        self.load_preset_button.setToolTip("Load preset connections")
        toolbar.addWidget(self.load_preset_button)
        
        self.delete_preset_button = QPushButton("🗑️")
        self.delete_preset_button.clicked.connect(self._delete_preset)
        self.delete_preset_button.setToolTip("Delete preset")
        toolbar.addWidget(self.delete_preset_button)
        
        # Canvas controls
        self.refresh_button = QPushButton("🔄 Refresh")
        self.refresh_button.clicked.connect(self._refresh_canvas)
        toolbar.addWidget(self.refresh_button)
        
        self.auto_arrange_button = QPushButton("📐 Arrange")
        self.auto_arrange_button.clicked.connect(self._auto_arrange)
        toolbar.addWidget(self.auto_arrange_button)
        
        self.zoom_fit_button = QPushButton("🔍 Fit")
        self.zoom_fit_button.clicked.connect(self._fit_all)
        toolbar.addWidget(self.zoom_fit_button)
        
        layout.addLayout(toolbar)
        
        # Canvas
        self.canvas = NodeCanvas(self)
        self.canvas.connection_requested.connect(self._on_connection_requested)
        self.canvas.disconnection_requested.connect(self._on_disconnection_requested)
        layout.addWidget(self.canvas)
        
        # Minimap temporarily disabled
        # # Create minimap overlay
        # self.minimap = MiniMapView(self.canvas, self.canvas)
        # self.minimap.viewport_move_requested.connect(self._on_minimap_move)
        # self.canvas.viewport_changed.connect(self.minimap.update_viewport_rect)
        # 
        # # Position minimap in bottom-left corner
        # self.minimap.setParent(self.canvas)
        # self.minimap.move(10, self.canvas.height() - self.minimap.height() - 10)
        # self.minimap.raise_()  # Bring to front
        # self.minimap.show()
        # 
        # # Install event filter to reposition minimap on resize
        # self.canvas.installEventFilter(self)
    
    def set_jack_manager(self, jack_manager: Optional[JackClientManager]):
        """Set JACK manager and populate canvas."""
        self.jack_manager = jack_manager
        if jack_manager:
            self._refresh_canvas()
    
    # Minimap methods temporarily disabled
    # def eventFilter(self, obj, event):
    #     """Handle canvas resize to reposition minimap."""
    #     if obj == self.canvas and event.type() == event.Type.Resize:
    #         # Reposition minimap in bottom-left corner
    #         self.minimap.move(10, self.canvas.height() - self.minimap.height() - 10)
    #     return super().eventFilter(obj, event)
    # 
    # def _on_minimap_move(self, scene_pos: QPointF):
    #     """Handle minimap viewport drag."""
    #     # Center main view on the requested scene position
    #     self.canvas.centerOn(scene_pos)
    #     self.minimap.update_viewport_rect()
    
    def _refresh_canvas(self):
        """Refresh canvas from JACK state."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            logger.debug("Cannot refresh canvas: JACK not connected")
            return
        
        # Store current node positions
        old_positions = self.canvas.get_node_positions()
        
        # Clear and rebuild
        self.canvas.clear_all()
        
        # Get all ports
        try:
            output_ports = self.jack_manager.get_ports(is_output=True, is_audio=True)
            input_ports = self.jack_manager.get_ports(is_input=True, is_audio=True)
            logger.debug(f"Found {len(output_ports)} output ports and {len(input_ports)} input ports")
        except Exception as e:
            logger.error(f"Failed to get JACK ports: {e}")
            return
        
        # Create nodes for each client
        # Special handling: split "system" into separate input/output nodes
        clients = set()
        for port in output_ports + input_ports:
            client_name = port.split(':')[0]
            clients.add(client_name)
        
        for client_name in sorted(clients):
            # Check if this client has both inputs and outputs
            has_outputs = any(port.startswith(client_name + ':') for port in output_ports)
            has_inputs = any(port.startswith(client_name + ':') for port in input_ports)
            
            # Special case: split "system" into two nodes
            if client_name == "system" and has_outputs and has_inputs:
                # Create source node (capture ports - hardware inputs become JACK outputs)
                out_node_name = "system (capture)"
                x_out, y_out = old_positions.get(out_node_name, (None, None))
                out_node = self.canvas.add_node(out_node_name, x_out, y_out)
                
                for port in output_ports:
                    if port.startswith(client_name + ':'):
                        port_name = ':'.join(port.split(':')[1:])
                        port_item = out_node.add_output_port(port_name)
                        # Update full name to match actual JACK port
                        port_item.full_name = f"{client_name}:{port_name}"
                
                # Create sink node (playback ports - hardware outputs become JACK inputs)
                in_node_name = "system (playback)"
                x_in, y_in = old_positions.get(in_node_name, (None, None))
                in_node = self.canvas.add_node(in_node_name, x_in, y_in)
                
                for port in input_ports:
                    if port.startswith(client_name + ':'):
                        port_name = ':'.join(port.split(':')[1:])
                        port_item = in_node.add_input_port(port_name)
                        # Update full name to match actual JACK port
                        port_item.full_name = f"{client_name}:{port_name}"
            else:
                # Normal client - single node
                x, y = old_positions.get(client_name, (None, None))
                node = self.canvas.add_node(client_name, x, y)
                
                # Add output ports
                for port in output_ports:
                    if port.startswith(client_name + ':'):
                        port_name = ':'.join(port.split(':')[1:])
                        node.add_output_port(port_name)
                
                # Add input ports
                for port in input_ports:
                    if port.startswith(client_name + ':'):
                        port_name = ':'.join(port.split(':')[1:])
                        node.add_input_port(port_name)
        
        # Add connections
        try:
            connections = self.jack_manager.get_all_connections()
            for output_port, input_ports in connections.items():
                for input_port in input_ports:
                    self.canvas.add_connection(output_port, input_port)
        except Exception as e:
            logger.error(f"Failed to get JACK connections: {e}")
        
        # Minimap update disabled
        # self.minimap.refit_minimap()
        # self.minimap.update_viewport_rect()
    
    def _auto_refresh(self):
        """Auto-refresh if enabled."""
        if self.jack_manager and self.jack_manager.is_connected():
            self._refresh_canvas()
    
    def _auto_arrange(self):
        """Auto-arrange nodes in a grid."""
        x, y = 50, 50
        for node in self.canvas.nodes.values():
            node.setPos(x, y)
            x += 200
            if x > 800:
                x = 50
                y += 150
        
        # Update connections
        for conn in self.canvas.connections:
            conn.update_position()
    
    def _fit_all(self):
        """Fit all nodes in view."""
        self.canvas.fitInView(self.canvas.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
        # Minimap update disabled
        # self.minimap.refit_minimap()
        # self.minimap.update_viewport_rect()
    
    def _on_connection_requested(self, output_port: str, input_port: str):
        """Handle connection request."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            return
        
        try:
            self.jack_manager.connect_ports(output_port, input_port)
            self.canvas.add_connection(output_port, input_port)
            logger.info(f"Connected {output_port} -> {input_port}")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            QMessageBox.warning(self, "Connection Failed", f"Could not connect ports:\n{e}")
    
    def _on_disconnection_requested(self, output_port: str, input_port: str):
        """Handle disconnection request."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            return
        
        try:
            self.jack_manager.disconnect_ports(output_port, input_port)
            self.canvas.remove_connection(output_port, input_port)
            logger.info(f"Disconnected {output_port} -> {input_port}")
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
    
    def _save_preset(self):
        """Save current connection state as preset."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            QMessageBox.warning(self, "Not Connected", "JACK is not connected.")
            return
        
        # Ask for preset name
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name:
            return
        
        # Sanitize filename
        filename = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        if not filename:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid preset name.")
            return
        
        preset_path = self.presets_dir / f"{filename}.json"
        
        # Gather connection data
        try:
            connections = self.jack_manager.get_all_connections()
            node_positions = self.canvas.get_node_positions()
            
            preset_data = {
                "name": name,
                "connections": [
                    {"output": out, "input": inp}
                    for out, inputs in connections.items()
                    for inp in inputs
                ],
                "node_positions": {
                    name: {"x": x, "y": y}
                    for name, (x, y) in node_positions.items()
                }
            }
            
            # Save to file
            with open(preset_path, 'w') as f:
                json.dump(preset_data, f, indent=2)
            
            logger.info(f"Saved preset: {preset_path}")
            QMessageBox.information(self, "Preset Saved", f"Preset '{name}' saved successfully!")
            self._refresh_preset_list()
            
        except Exception as e:
            logger.error(f"Failed to save preset: {e}")
            QMessageBox.critical(self, "Save Failed", f"Could not save preset:\n{e}")
    
    def _load_preset(self):
        """Load preset connections."""
        if not self.jack_manager or not self.jack_manager.is_connected():
            QMessageBox.warning(self, "Not Connected", "JACK is not connected.")
            return
        
        preset_name = self.preset_combo.currentText()
        if not preset_name:
            QMessageBox.warning(self, "No Preset", "Please select a preset to load.")
            return
        
        # Find preset file
        preset_files = list(self.presets_dir.glob("*.json"))
        preset_path = None
        for path in preset_files:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if data.get("name") == preset_name:
                        preset_path = path
                        break
            except:
                continue
        
        if not preset_path:
            QMessageBox.warning(self, "Preset Not Found", f"Could not find preset '{preset_name}'.")
            return
        
        try:
            with open(preset_path, 'r') as f:
                preset_data = json.load(f)
            
            # Load node positions if available
            if "node_positions" in preset_data:
                positions = {
                    name: (pos["x"], pos["y"])
                    for name, pos in preset_data["node_positions"].items()
                }
                self.canvas.set_node_positions(positions)
            
            # Load connections
            connections = preset_data.get("connections", [])
            success_count = 0
            failed_count = 0
            failed_connections = []
            
            for conn in connections:
                output_port = conn["output"]
                input_port = conn["input"]
                
                try:
                    # Check if ports exist
                    output_client = output_port.split(':')[0]
                    input_client = input_port.split(':')[0]
                    
                    if output_client not in self.canvas.nodes or input_client not in self.canvas.nodes:
                        failed_count += 1
                        failed_connections.append(f"{output_port} -> {input_port} (node not found)")
                        continue
                    
                    # Try to connect
                    self.jack_manager.connect_ports(output_port, input_port)
                    self.canvas.add_connection(output_port, input_port)
                    success_count += 1
                    
                except Exception as e:
                    failed_count += 1
                    failed_connections.append(f"{output_port} -> {input_port} ({e})")
            
            # Show results
            message = f"Loaded preset '{preset_name}':\n"
            message += f"✓ {success_count} connections restored\n"
            if failed_count > 0:
                message += f"✗ {failed_count} connections failed\n\n"
                message += "Failed connections:\n"
                message += "\n".join(failed_connections[:10])  # Show first 10
                if len(failed_connections) > 10:
                    message += f"\n... and {len(failed_connections) - 10} more"
            
            if failed_count > 0:
                QMessageBox.warning(self, "Preset Loaded (Partial)", message)
            else:
                QMessageBox.information(self, "Preset Loaded", message)
            
            logger.info(f"Loaded preset: {preset_path} ({success_count} connections, {failed_count} failed)")
            
        except Exception as e:
            logger.error(f"Failed to load preset: {e}")
            QMessageBox.critical(self, "Load Failed", f"Could not load preset:\n{e}")
    
    def _delete_preset(self):
        """Delete selected preset."""
        preset_name = self.preset_combo.currentText()
        if not preset_name:
            QMessageBox.warning(self, "No Preset", "Please select a preset to delete.")
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Are you sure you want to delete preset '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Find and delete preset file
        preset_files = list(self.presets_dir.glob("*.json"))
        for path in preset_files:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if data.get("name") == preset_name:
                        path.unlink()
                        logger.info(f"Deleted preset: {path}")
                        QMessageBox.information(self, "Preset Deleted", f"Preset '{preset_name}' deleted.")
                        self._refresh_preset_list()
                        return
            except:
                continue
        
        QMessageBox.warning(self, "Delete Failed", f"Could not find preset file for '{preset_name}'.")
    
    def _refresh_preset_list(self):
        """Refresh preset dropdown."""
        current = self.preset_combo.currentText()
        self.preset_combo.clear()
        
        # Load preset names from files
        preset_files = list(self.presets_dir.glob("*.json"))
        preset_names = []
        
        for path in preset_files:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    name = data.get("name", path.stem)
                    preset_names.append(name)
            except:
                continue
        
        preset_names.sort()
        self.preset_combo.addItems(preset_names)
        
        # Restore selection if possible
        index = self.preset_combo.findText(current)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
