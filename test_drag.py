#!/usr/bin/env python3
"""Minimal test to isolate node dragging issue."""

import sys
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor

class TestNode(QGraphicsRectItem):
    def __init__(self, x, y):
        super().__init__(0, 0, 100, 60)
        self.setPos(x, y)
        self.setBrush(QColor(100, 100, 100))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsScenePositionChanges)
    
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            print(f"Node moved to: {value.toPointF()}")
        return super().itemChange(change, value)

class TestView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        # Add test nodes
        self.scene.addItem(TestNode(100, 100))
        self.scene.addItem(TestNode(300, 200))
    
    def wheelEvent(self, event):
        f = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    view = TestView()
    view.resize(800, 600)
    view.setWindowTitle("Drag Test - Should work perfectly")
    view.show()
    sys.exit(app.exec())
