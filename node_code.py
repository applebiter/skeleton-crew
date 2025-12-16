import sys
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor

class Socket(QGraphicsItem):
    """Small interactive circles on nodes for connections."""
    def __init__(self, parent, is_input=True):
        super().__init__(parent)
        self.is_input = is_input
        self.radius = 6
        self.edges = []
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        return QRectF(-self.radius, -self.radius, 2 * self.radius, 2 * self.radius)

    def paint(self, painter, option, widget):
        painter.setBrush(QColor("#f1c40f"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.boundingRect())

    def mousePressEvent(self, event):
        # Start drawing a new connection line
        self.scene().start_connection(self)
        event.accept()

class Edge(QGraphicsPathItem):
    """A Bezier curve connecting two sockets."""
    def __init__(self, start_socket, end_socket=None):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket
        self.setPen(QPen(QColor("#ecf0f1"), 2))
        self.setZValue(-1) # Draw behind nodes

    def update_path(self, target_pos=None):
        path = QPainterPath()
        start_pos = self.start_socket.scenePos()
        end_pos = target_pos if target_pos else self.end_socket.scenePos()
        
        path.moveTo(start_pos)
        # Control points for the Bezier curve
        dist = abs(end_pos.x() - start_pos.x()) * 0.5
        path.cubicTo(start_pos.x() + dist, start_pos.y(),
                     end_pos.x() - dist, end_pos.y(),
                     end_pos.x(), end_pos.y())
        self.setPath(path)

class Node(QGraphicsItem):
    """A node containing an input and output socket."""
    def __init__(self, x, y, title="Node"):
        super().__init__()
        self.setPos(x, y)
        self.width, self.height = 120, 80
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsScenePositionChanges)
        
        # Add Sockets
        self.input_socket = Socket(self, is_input=True)
        self.input_socket.setPos(0, self.height/2)
        
        self.output_socket = Socket(self, is_input=False)
        self.output_socket.setPos(self.width, self.height/2)

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget):
        painter.setBrush(QColor("#2c3e50"))
        painter.setPen(QPen(QColor("#34495e"), 2))
        painter.drawRoundedRect(self.boundingRect(), 10, 10)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for socket in [self.input_socket, self.output_socket]:
                for edge in socket.edges:
                    edge.update_path()
        return super().itemChange(change, value)

class NodeCanvasScene(QGraphicsScene):
    """Scene managing the dragging logic for connections."""
    def __init__(self):
        super().__init__(-2000, -2000, 4000, 4000)
        self.dragging_edge = None
        self.source_socket = None

    def start_connection(self, socket):
        self.source_socket = socket
        self.dragging_edge = Edge(socket)
        self.addItem(self.dragging_edge)

    def mouseMoveEvent(self, event):
        if self.dragging_edge:
            self.dragging_edge.update_path(event.scenePos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging_edge:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(item, Socket) and item != self.source_socket:
                # Successful connection
                self.dragging_edge.end_socket = item
                self.source_socket.edges.append(self.dragging_edge)
                item.edges.append(self.dragging_edge)
                self.dragging_edge.update_path()
            else:
                # Cancelled connection
                self.removeItem(self.dragging_edge)
            self.dragging_edge = None
        super().mouseReleaseEvent(event)

class NodeCanvas(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = NodeCanvasScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        self.scene.addItem(Node(50, 50))
        self.scene.addItem(Node(250, 150))

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = NodeCanvas()
    v.resize(800, 600); v.show()
    sys.exit(app.exec())
