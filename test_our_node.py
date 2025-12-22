#!/usr/bin/env python3
"""Test our actual NodeGraphicsItem to isolate the issue."""

import sys
from dataclasses import dataclass, field
from typing import List
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

@dataclass
class PortModel:
    name: str
    full_name: str
    is_output: bool

@dataclass
class NodeModel:
    name: str
    inputs: List[PortModel] = field(default_factory=list)
    outputs: List[PortModel] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0

class NodeGraphicsItem(QGraphicsItem):
    """Exact copy from node_canvas_v3.py"""
    
    def __init__(self, model: NodeModel):
        super().__init__()
        self.model = model
        
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
        painter.setBrush(QColor(50, 50, 50))
        painter.setPen(QPen(QColor(200, 200, 200), 2))
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Sans", 9, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(5, 5, self.width - 10, 20), Qt.AlignLeft, self.model.name)
    
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            pos = value.toPointF() if hasattr(value, 'toPointF') else self.pos()
            self.model.x = pos.x()
            self.model.y = pos.y()
            print(f"Node {self.model.name} moved to: {pos.x():.1f}, {pos.y():.1f}")
        return super().itemChange(change, value)

class TestView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        # Add test nodes
        node1 = NodeModel("Test Node 1", x=100, y=100)
        node2 = NodeModel("Test Node 2", x=300, y=200)
        
        self.scene.addItem(NodeGraphicsItem(node1))
        self.scene.addItem(NodeGraphicsItem(node2))
    
    def wheelEvent(self, event):
        f = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(f, f)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    view = TestView()
    view.resize(800, 600)
    view.setWindowTitle("Test Our NodeGraphicsItem")
    view.show()
    sys.exit(app.exec())
