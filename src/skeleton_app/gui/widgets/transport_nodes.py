"""
Transport node widgets for the node canvas.

These nodes allow visual representation and control of transport agents and coordinators.
"""

import logging
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QListWidget, QGroupBox, QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from skeleton_app.audio.transport_services import TransportAgentService, TransportCoordinatorService
from skeleton_app.service_discovery import ServiceStatus, HealthStatus

logger = logging.getLogger(__name__)


class TransportAgentNodeWidget(QWidget):
    """
    Node widget for a TransportAgent.
    
    Displays status and provides basic control/monitoring.
    """
    
    status_changed = Signal(str)  # For updating canvas node appearance
    
    def __init__(self, service: TransportAgentService, parent=None):
        super().__init__(parent)
        self.service = service
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header
        header = QLabel(f"Transport Agent")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)
        
        # Status indicators
        self.status_label = QLabel(f"Status: {self.service.status.value}")
        self.health_label = QLabel(f"Health: {self.service.health.value}")
        layout.addWidget(self.status_label)
        layout.addWidget(self.health_label)
        
        # OSC info
        info_label = QLabel(f"OSC Port: {self.service.osc_port}")
        info_label.setStyleSheet("font-size: 9pt; color: #888;")
        layout.addWidget(info_label)
        
        # State display (updated by agent)
        self.state_label = QLabel("State: unknown")
        self.state_label.setStyleSheet("font-size: 9pt;")
        layout.addWidget(self.state_label)
        
        # Log display (last message)
        log_group = QGroupBox("Last Message")
        log_layout = QVBoxLayout(log_group)
        self.log_label = QLabel("(no messages)")
        self.log_label.setWordWrap(True)
        self.log_label.setStyleSheet("font-size: 8pt; color: #666;")
        log_layout.addWidget(self.log_label)
        layout.addWidget(log_group)
    
    def _connect_signals(self):
        """Connect service signals."""
        self.service.status_changed.connect(self._on_status_changed)
        self.service.health_changed.connect(self._on_health_changed)
        self.service.log.connect(self._on_log)
        self.service.error.connect(self._on_error)
        
        if self.service.agent:
            self.service.agent.state_changed.connect(self._on_state_changed)
    
    def _on_status_changed(self, status: ServiceStatus):
        """Update status display."""
        self.status_label.setText(f"Status: {status.value}")
        self._update_colors()
        self.status_changed.emit(status.value)
    
    def _on_health_changed(self, health: HealthStatus):
        """Update health display."""
        self.health_label.setText(f"Health: {health.value}")
        self._update_colors()
    
    def _on_log(self, message: str):
        """Display log message."""
        self.log_label.setText(message)
        self.log_label.setStyleSheet("font-size: 8pt; color: #00aa00;")
    
    def _on_error(self, message: str):
        """Display error message."""
        self.log_label.setText(f"ERROR: {message}")
        self.log_label.setStyleSheet("font-size: 8pt; color: #cc0000;")
    
    def _on_state_changed(self, state: Dict):
        """Update transport state display."""
        self.state_label.setText(
            f"State: {state.get('state', 'unknown')} @ frame {state.get('frame', 0)}"
        )
    
    def _update_colors(self):
        """Update widget colors based on status/health."""
        if self.service.health == HealthStatus.HEALTHY:
            color = "#00aa00"
        elif self.service.health == HealthStatus.DEGRADED:
            color = "#aaaa00"
        else:
            color = "#cc0000"
        
        self.health_label.setStyleSheet(f"color: {color};")
    
    def get_node_color(self) -> QColor:
        """Get color for canvas node representation."""
        if self.service.status == ServiceStatus.AVAILABLE:
            if self.service.health == HealthStatus.HEALTHY:
                return QColor(100, 200, 100)  # Green
            else:
                return QColor(200, 200, 100)  # Yellow
        else:
            return QColor(200, 100, 100)  # Red


class TransportCoordinatorNodeWidget(QWidget):
    """
    Node widget for a TransportCoordinator.
    
    Provides control panel for coordinating multiple agents.
    """
    
    status_changed = Signal(str)
    
    def __init__(self, service: TransportCoordinatorService, parent=None):
        super().__init__(parent)
        self.service = service
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header
        header = QLabel("Transport Coordinator")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)
        
        # Status
        self.status_label = QLabel(f"Status: {self.service.status.value}")
        layout.addWidget(self.status_label)
        
        # Pre-roll control
        preroll_layout = QHBoxLayout()
        preroll_layout.addWidget(QLabel("Pre-roll (s):"))
        self.preroll_spin = QDoubleSpinBox()
        self.preroll_spin.setRange(0.0, 10.0)
        self.preroll_spin.setValue(3.0)
        self.preroll_spin.setSingleStep(0.5)
        self.preroll_spin.setDecimals(1)
        preroll_layout.addWidget(self.preroll_spin)
        layout.addLayout(preroll_layout)
        
        # Frame control
        frame_layout = QHBoxLayout()
        frame_layout.addWidget(QLabel("Frame:"))
        self.frame_spin = QSpinBox()
        self.frame_spin.setRange(0, 999999999)
        self.frame_spin.setValue(0)
        frame_layout.addWidget(self.frame_spin)
        layout.addLayout(frame_layout)
        
        # Control buttons
        btn_group = QGroupBox("Transport Control")
        btn_layout = QVBoxLayout(btn_group)
        
        self.btn_start = QPushButton("▶ Start All")
        self.btn_start.clicked.connect(self._on_start_clicked)
        btn_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton("⏹ Stop All")
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.btn_stop)
        
        self.btn_locate_start = QPushButton("⏮ Locate & Start")
        self.btn_locate_start.clicked.connect(self._on_locate_start_clicked)
        btn_layout.addWidget(self.btn_locate_start)
        
        self.btn_locate = QPushButton("⏮ Locate")
        self.btn_locate.clicked.connect(self._on_locate_clicked)
        btn_layout.addWidget(self.btn_locate)
        
        layout.addWidget(btn_group)
        
        # Agents list
        agents_group = QGroupBox("Agents")
        agents_layout = QVBoxLayout(agents_group)
        
        # Add agent controls
        add_layout = QHBoxLayout()
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("Host/IP")
        add_layout.addWidget(self.host_input)
        
        self.add_btn = QPushButton("+")
        self.add_btn.setMaximumWidth(30)
        self.add_btn.clicked.connect(self._on_add_agent_clicked)
        add_layout.addWidget(self.add_btn)
        agents_layout.addLayout(add_layout)
        
        # Agents list
        self.agents_list = QListWidget()
        self.agents_list.setMaximumHeight(100)
        agents_layout.addWidget(self.agents_list)
        
        layout.addWidget(agents_group)
        
        # Log display
        self.log_label = QLabel("(no messages)")
        self.log_label.setWordWrap(True)
        self.log_label.setStyleSheet("font-size: 8pt; color: #666;")
        layout.addWidget(self.log_label)
        
        # Update agents list
        self._update_agents_list()
    
    def _connect_signals(self):
        """Connect service signals."""
        self.service.status_changed.connect(self._on_status_changed)
        self.service.log.connect(self._on_log)
        self.service.error.connect(self._on_error)
    
    def _on_start_clicked(self):
        """Handle Start All button."""
        pre_roll = self.preroll_spin.value()
        self.service.start_all(pre_roll)
    
    def _on_stop_clicked(self):
        """Handle Stop All button."""
        self.service.stop_all()
    
    def _on_locate_start_clicked(self):
        """Handle Locate & Start button."""
        frame = self.frame_spin.value()
        pre_roll = self.preroll_spin.value()
        self.service.locate_and_start_all(frame, pre_roll)
    
    def _on_locate_clicked(self):
        """Handle Locate button."""
        frame = self.frame_spin.value()
        self.service.locate_all(frame)
    
    def _on_add_agent_clicked(self):
        """Handle add agent button."""
        host = self.host_input.text().strip()
        if host:
            self.service.add_agent(host)
            self.host_input.clear()
            self._update_agents_list()
    
    def _update_agents_list(self):
        """Update the agents list display."""
        self.agents_list.clear()
        for agent in self.service.get_agents():
            self.agents_list.addItem(f"{agent.name} ({agent.host}:{agent.port})")
    
    def _on_status_changed(self, status: ServiceStatus):
        """Update status display."""
        self.status_label.setText(f"Status: {status.value}")
        self.status_changed.emit(status.value)
    
    def _on_log(self, message: str):
        """Display log message."""
        self.log_label.setText(message)
        self.log_label.setStyleSheet("font-size: 8pt; color: #00aa00;")
    
    def _on_error(self, message: str):
        """Display error message."""
        self.log_label.setText(f"ERROR: {message}")
        self.log_label.setStyleSheet("font-size: 8pt; color: #cc0000;")
    
    def get_node_color(self) -> QColor:
        """Get color for canvas node representation."""
        if self.service.status == ServiceStatus.AVAILABLE:
            return QColor(100, 150, 200)  # Blue
        else:
            return QColor(200, 100, 100)  # Red
