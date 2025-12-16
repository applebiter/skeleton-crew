import sys
from PySide6.QtWidgets import (QApplication, QGraphicsView, QGraphicsScene, 
                             QGraphicsRectItem, QGraphicsItem)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QWheelEvent

class Node(QGraphicsRectItem):
    """A basic draggable node."""
    def __init__(self, x, y):
        super().__init__(0, 0, 100, 60)
        self.setPos(x, y)
        self.setBrush(Qt.lightGray)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)

class NodeCanvas(QGraphicsView):
    """The view/viewport for the node graph."""
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        
        # Performance & Visual optimizations
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse) # Essential for zoom
        
        # Add sample nodes
        self.scene.addItem(Node(50, 50))
        self.scene.addItem(Node(200, 100))

    def wheelEvent(self, event: QWheelEvent):
        """Zoom to mouse position based on scroll direction."""
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

    def mousePressEvent(self, event):
        """Enable canvas panning with middle mouse button."""
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            # Manually trigger the event to start the drag immediately
            fake_event = QWheelEvent(event.position(), event.globalPosition(), 
                                    event.pixelDelta(), event.angleDelta(), 
                                    event.buttons(), Qt.NoModifier, Qt.NoPhase, False)
            super().mousePressEvent(event)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Reset drag mode when middle mouse is released."""
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.NoDrag)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    view = NodeCanvas()
    view.setWindowTitle("PySide6 Node Canvas")
    view.resize(800, 600)
    view.show()
    sys.exit(app.exec())
