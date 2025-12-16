from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
import sys

class Node(QGraphicsRectItem):
    def __init__(self, x, y):
        super().__init__(0, 0, 100, 60)
        self.setPos(x, y)
        self.setBrush(Qt.lightGray)
        # These flags are what let you move the actual nodes
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)

class NodeCanvas(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.Antialiasing)
        # Essential to keep the zoom centered on the mouse
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        # Add nodes
        self.scene.addItem(Node(0, 0))
        self.scene.addItem(Node(150, 50))

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        
        if item is None:
            # CLICKED ON BACKGROUND: Enable panning
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        else:
            # CLICKED ON A NODE: Disable panning so the node can be dragged
            self.setDragMode(QGraphicsView.NoDrag)
            
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # Always reset drag mode on release to keep selection working
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.NoDrag)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    v = NodeCanvas()
    v.show()
    sys.exit(app.exec())
