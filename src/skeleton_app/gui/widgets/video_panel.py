"""
Video player management panel.

Shows active Qt video players and allows control.
"""

import logging
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QGroupBox, QScrollArea,
    QSplitter
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtMultimedia import QMediaPlayer

from skeleton_app.audio.qt_video_player import QtVideoPlayerManager, QtVideoPlayer
from skeleton_app.gui.widgets.video_player_widget import VideoPlayerWidget

logger = logging.getLogger(__name__)


class VideoPanel(QWidget):
    """
    Video player management panel.
    
    Shows active Qt video players and provides controls.
    """
    
    # Signals
    video_opened = Signal(str, str)  # instance_id, file_path
    video_closed = Signal(str)  # instance_id
    
    def __init__(self, video_manager: QtVideoPlayerManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.video_manager = video_manager
        self.player_widgets: Dict[str, VideoPlayerWidget] = {}
        self._setup_ui()
        
        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_instances)
        self.refresh_timer.start(2000)  # Update every 2 seconds
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header with open button
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Video Players</b>")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Open video button
        self.open_button = QPushButton("Open Video")
        self.open_button.clicked.connect(self._on_open_video)
        header_layout.addWidget(self.open_button)
        
        layout.addLayout(header_layout)
        
        # Video players scroll area
        self.players_scroll = QScrollArea()
        self.players_scroll.setWidgetResizable(True)
        self.players_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.players_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Container for player widgets
        self.players_container = QWidget()
        self.players_layout = QVBoxLayout(self.players_container)
        self.players_layout.addStretch()
        
        self.players_scroll.setWidget(self.players_container)
        layout.addWidget(self.players_scroll)
        
        # Info box
        info_box = QGroupBox("Info")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "Qt Multimedia video players sync to JACK transport.\n"
            "Videos are embedded by default, detach for multi-monitor.\n"
            "Audio muted by default (JACK handles audio routing).\n"
            "Circular buffer ensures smooth, frame-accurate sync."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        info_box.setLayout(info_layout)
        layout.addWidget(info_box)
    
    def _on_open_video(self):
        """Handle open video button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video File",
            str(Path.home()),
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.ogv *.flv *.wmv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # Create player with video file
            instance_id, player = self.video_manager.create_player(
                file_path=Path(file_path),
                sync_enabled=True
            )
            
            # Start playback
            player.play()
            
            # Create embedded player widget
            player_widget = VideoPlayerWidget(player, self)
            player_widget.closed.connect(self._on_player_closed)
            
            # Add to layout (before the stretch)
            self.players_layout.insertWidget(self.players_layout.count() - 1, player_widget)
            
            # Store reference
            self.player_widgets[instance_id] = player_widget
            
            logger.info(f"Opened video: {file_path} (instance: {instance_id})")
            self.video_opened.emit(instance_id, file_path)
            
        except Exception as e:
            logger.error(f"Failed to open video: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open video:\n{str(e)}"
            )
    
    def _on_player_closed(self, instance_id: str):
        """Handle video player widget close."""
        widget = self.player_widgets.pop(instance_id, None)
        if widget:
            widget.cleanup()
            widget.deleteLater()
        
        self.video_manager.remove_player(instance_id)
        self.video_closed.emit(instance_id)
        logger.info(f"Closed video player: {instance_id}")
    
    def _on_stop_all(self):
        """Stop all video instances."""
        try:
            # Close all player widgets
            for instance_id in list(self.player_widgets.keys()):
                widget = self.player_widgets.pop(instance_id)
                widget.cleanup()
                widget.deleteLater()
                self.video_manager.remove_player(instance_id)
                self.video_closed.emit(instance_id)
            
            logger.info("Stopped all video instances")
        except Exception as e:
            logger.error(f"Failed to stop all instances: {e}")
    
    def _refresh_instances(self):
        """Refresh the instance list (no-op now that we have embedded widgets)."""
        # Instance widgets are now self-managing
        pass
