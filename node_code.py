import sys
import math
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem, QMenu
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QAction

GRID_SIZE = 20

class Socket(QGraphicsItem):
    def __init__(self, parent, is_input=True):
        super().__init__(parent)
        self.is_input = is_input
        self.edges = []
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        return QRectF(-6, -6, 12, 12)

    def paint(self, painter, option, widget):
        painter.setBrush(QColor("#f1c40f"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.boundingRect())

    def mousePressEvent(self, event):
        self.scene().start_connection(self)
        event.accept()

class Edge(QGraphicsPathItem):
    def __init__(self, start_socket, end_socket=None):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket
        self.setPen(QPen(QColor("#ecf0f1"), 2))
        self.setZValue(-1)
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsFocusable)

    def update_path(self, target_pos=None):
        path = QPainterPath()
        start_pos = self.start_socket.scenePos()
        end_pos = target_pos if target_pos else self.end_socket.scenePos()
        path.moveTo(start_pos)
        dist = abs(end_pos.x() - start_pos.x()) * 0.5
        path.cubicTo(start_pos.x() + dist, start_pos.y(), end_pos.x() - dist, end_pos.y(), end_pos.x(), end_pos.y())
        self.setPath(path)

    def paint(self, painter, option, widget):
        # Change color if selected to show it can be deleted
        color = QColor("#3498db") if self.isSelected() else QColor("#ecf0f1")
        self.setPen(QPen(color, 3 if self.isSelected() else 2))
        super().paint(painter, option, widget)

class Node(QGraphicsItem):
    def __init__(self, x, y, title="Node"):
        super().__init__()
        self.setPos(x, y)
        self.width, self.height = 120, 80
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsScenePositionChanges)
        self.input_socket = Socket(self, True)
        self.input_socket.setPos(0, 40)
        self.output_socket = Socket(self, False)
        self.output_socket.setPos(120, 40)

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget):
        painter.setBrush(QColor("#2c3e50"))
        painter.setPen(QPen(QColor("#34495e"), 2))
        painter.drawRoundedRect(self.boundingRect(), 10, 10)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # GRID SNAPPING LOGIC
            new_pos = value.toPointF()
            x = round(new_pos.x() / GRID_SIZE) * GRID_SIZE
            y = round(new_pos.y() / GRID_SIZE) * GRID_SIZE
            return QPointF(x, y)
        
        if change == QGraphicsItem.ItemPositionHasChanged:
            for s in [self.input_socket, self.output_socket]:
                for e in s.edges: e.update_path()
        return super().itemChange(change, value)

class NodeScene(QGraphicsScene):
    def __init__(self):
        super().__init__(-2000, -2000, 4000, 4000)
        self.dragging_edge = None
        self.source_socket = None

    def drawBackground(self, painter, rect):
        # VISUAL GRID
        painter.setPen(QPen(QColor("#3d3d3d"), 1))
        left, top = int(rect.left()), int(rect.top())
        for x in range(left - (left % GRID_SIZE), int(rect.right()), GRID_SIZE):
            painter.drawLine(x, rect.top(), x, rect.bottom())
        for y in range(top - (top % GRID_SIZE), int(rect.bottom()), GRID_SIZE):
            painter.drawLine(rect.left(), y, rect.right(), y)

    def start_connection(self, socket):
        self.source_socket = socket
        self.dragging_edge = Edge(socket)
        self.addItem(self.dragging_edge)

    def mouseMoveEvent(self, event):
        if self.dragging_edge: self.dragging_edge.update_path(event.scenePos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging_edge:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(item, Socket) and item != self.source_socket:
                self.dragging_edge.end_socket = item
                self.source_socket.edges.append(self.dragging_edge)
                item.edges.append(self.dragging_edge)
                self.dragging_edge.update_path()
            else:
                self.removeItem(self.dragging_edge)
            self.dragging_edge = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        # DELETE LOGIC
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.selectedItems():
                if isinstance(item, Edge):
                    item.start_socket.edges.remove(item)
                    item.end_socket.edges.remove(item)
                    self.removeItem(item)
                elif isinstance(item, Node):
                    self.removeItem(item)
        super().keyPressEvent(event)

class NodeView(QGraphicsView):
    def __init__(self):
        super().__init__(NodeScene())
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scene().addItem(Node(100, 100))
        self.scene().addItem(Node(300, 200))

    def wheelEvent(self, event):
        f = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = NodeView()
    v.show()
    sys.exit(app.exec())
