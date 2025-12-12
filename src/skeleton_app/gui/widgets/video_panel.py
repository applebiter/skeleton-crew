"""
Video player management panel.

Shows active Qt video players and allows control.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QGroupBox, QDialog
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtMultimedia import QMediaPlayer

from skeleton_app.audio.qt_video_player import QtVideoPlayerManager, QtVideoPlayer

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
        self._setup_ui()
        
        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_instances)
        self.refresh_timer.start(2000)  # Update every 2 seconds
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Video Players</b>")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Open video button
        self.open_button = QPushButton("Open Video")
        self.open_button.clicked.connect(self._on_open_video)
        header_layout.addWidget(self.open_button)
        
        layout.addLayout(header_layout)
        
        # Instance tree
        self.instance_tree = QTreeWidget()
        self.instance_tree.setHeaderLabels(["Instance", "File", "Status", "Sync"])
        self.instance_tree.setColumnWidth(0, 100)
        self.instance_tree.setColumnWidth(1, 250)
        self.instance_tree.setColumnWidth(2, 80)
        self.instance_tree.setColumnWidth(3, 100)
        layout.addWidget(self.instance_tree)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.stop_button = QPushButton("Stop Selected")
        self.stop_button.clicked.connect(self._on_stop_selected)
        button_layout.addWidget(self.stop_button)
        
        self.stop_all_button = QPushButton("Stop All")
        self.stop_all_button.clicked.connect(self._on_stop_all)
        button_layout.addWidget(self.stop_all_button)
        
        button_layout.addStretch()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_instances)
        button_layout.addWidget(self.refresh_button)
        
        layout.addLayout(button_layout)
        
        # Info box
        info_box = QGroupBox("Info")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "Qt Multimedia video players sync to JACK transport.\n"
            "Open multiple videos for multi-monitor setups.\n"
            "All instances follow the same timeline.\n"
            "Circular buffer ensures smooth, frame-accurate sync."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        info_box.setLayout(info_layout)
        layout.addWidget(info_box)
        
        # Initial refresh
        self._refresh_instances()
    
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
            
            # Create video widget window
            video_window = QDialog(self)
            video_window.setWindowTitle(f"{Path(file_path).name} - {instance_id}")
            video_window.setMinimumSize(800, 600)
            
            layout = QVBoxLayout()
            video_widget = player.create_video_widget(video_window)
            layout.addWidget(video_widget)
            video_window.setLayout(layout)
            
            # Show window
            video_window.show()
            
            # Store reference to keep window alive
            if not hasattr(self, '_video_windows'):
                self._video_windows = {}
            self._video_windows[instance_id] = video_window
            
            # Connect cleanup
            video_window.finished.connect(lambda: self._on_window_closed(instance_id))
            
            logger.info(f"Opened video: {file_path} (instance: {instance_id})")
            self.video_opened.emit(instance_id, file_path)
            self._refresh_instances()
            
        except Exception as e:
            logger.error(f"Failed to open video: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open video:\n{str(e)}"
            )
    
    def _on_window_closed(self, instance_id: str):
        """Handle video window close."""
        if hasattr(self, '_video_windows'):
            self._video_windows.pop(instance_id, None)
        self.video_manager.remove_player(instance_id)
        self.video_closed.emit(instance_id)
        self._refresh_instances()
    
    def _on_stop_selected(self):
        """Stop selected video instance."""
        selected_items = self.instance_tree.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            instance_id = item.text(0)
            try:
                # Close window if exists
                if hasattr(self, '_video_windows'):
                    window = self._video_windows.pop(instance_id, None)
                    if window:
                        window.close()
                
                self.video_manager.remove_player(instance_id)
                logger.info(f"Stopped video instance: {instance_id}")
                self.video_closed.emit(instance_id)
            except Exception as e:
                logger.error(f"Failed to stop instance {instance_id}: {e}")
        
        self._refresh_instances()
    
    def _on_stop_all(self):
        """Stop all video instances."""
        try:
            # Close all windows
            if hasattr(self, '_video_windows'):
                for window in list(self._video_windows.values()):
                    window.close()
                self._video_windows.clear()
            
            # Cleanup all players
            for instance_id in list(self.video_manager.get_all_players().keys()):
                self.video_manager.remove_player(instance_id)
                self.video_closed.emit(instance_id)
            
            logger.info("Stopped all video instances")
            self._refresh_instances()
        except Exception as e:
            logger.error(f"Failed to stop all instances: {e}")
    
    def _refresh_instances(self):
        """Refresh the instance list."""
        self.instance_tree.clear()
        
        players = self.video_manager.get_all_players()
        for instance_id, player in players.items():
            # Get player state
            playback_state = player.player.playbackState()
            if playback_state == QMediaPlayer.PlaybackState.PlayingState:
                state = "Playing"
            elif playback_state == QMediaPlayer.PlaybackState.PausedState:
                state = "Paused"
            else:
                state = "Stopped"
            
            # Get sync state
            stats = player.get_sync_stats()
            sync_text = f"{stats.state.value} ({stats.drift_ms:.1f}ms)"
            
            # Get file name
            file_name = player.file_path.name if player.file_path else "No file"
            
            item = QTreeWidgetItem([
                instance_id,
                file_name,
                state,
                sync_text
            ])
            
            # Color code sync state
            if stats.state.value == "synced":
                item.setForeground(3, Qt.green)
            elif stats.state.value == "syncing":
                item.setForeground(3, Qt.yellow)
            elif stats.state.value == "drift":
                item.setForeground(3, Qt.yellow)
            else:
                item.setForeground(3, Qt.red)
            
            self.instance_tree.addTopLevelItem(item)
        
        # Update button states
        has_instances = len(players) > 0
        self.stop_button.setEnabled(has_instances)
        self.stop_all_button.setEnabled(has_instances)
