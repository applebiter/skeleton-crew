"""
Video player management panel.

Shows active Qt video players and provides control.
Manages video tabs in the main window.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QGroupBox, QTabWidget
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtMultimedia import QMediaPlayer

from skeleton_app.audio.qt_video_player import QtVideoPlayerManager, QtVideoPlayer
from skeleton_app.gui.widgets.video_player_widget import VideoPlayerWidget
from skeleton_app.gui.widgets.screen_capture_widget import ScreenCaptureWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTabWidget

logger = logging.getLogger(__name__)


class VideoPanel(QWidget):
    """
    Video player management panel.
    
    Shows active Qt video players and provides controls.
    Opens videos as tabs in the main tab widget.
    """
    
    # Signals
    video_opened = Signal(str, str)  # instance_id, file_path
    video_closed = Signal(str)  # instance_id
    
    def __init__(
        self, 
        video_manager: QtVideoPlayerManager, 
        tab_widget: QTabWidget,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.video_manager = video_manager
        self.tab_widget = tab_widget
        self.video_tabs: Dict[str, int] = {}  # instance_id -> tab_index
        self.player_widgets: Dict[str, VideoPlayerWidget] = {}
        self.capture_widgets: Dict[str, ScreenCaptureWidget] = {}  # instance_id -> capture widget
        self.capture_counter = 0
        self._setup_ui()
        
        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_list)
        self.refresh_timer.start(2000)  # Update every 2 seconds
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header with open buttons
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Video Players</b>")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Open video button (Qt player - regular watching)
        self.open_button = QPushButton("📺 Open Video")
        self.open_button.clicked.connect(self._on_open_video)
        self.open_button.setToolTip("Open video in Qt player for regular watching")
        header_layout.addWidget(self.open_button)
        
        # Open in xjadeo button (frame-accurate work)
        self.open_xjadeo_button = QPushButton("🎬 Open in xjadeo")
        self.open_xjadeo_button.clicked.connect(self._on_open_xjadeo)
        self.open_xjadeo_button.setToolTip("Open transcoded video for frame-accurate work (requires transcode)")
        header_layout.addWidget(self.open_xjadeo_button)
        
        # Screen capture button
        self.capture_button = QPushButton("📹 Screen Capture")
        self.capture_button.clicked.connect(self._on_screen_capture)
        header_layout.addWidget(self.capture_button)
        
        layout.addLayout(header_layout)
        
        # Video list (tree widget showing open videos)
        self.video_tree = QTreeWidget()
        self.video_tree.setHeaderLabels(["Video", "Status", "Sync"])
        self.video_tree.setColumnWidth(0, 200)
        self.video_tree.setColumnWidth(1, 80)
        layout.addWidget(self.video_tree)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.close_button = QPushButton("Close Selected")
        self.close_button.clicked.connect(self._on_close_selected)
        button_layout.addWidget(self.close_button)
        
        self.close_all_button = QPushButton("Close All")
        self.close_all_button.clicked.connect(self._on_close_all)
        button_layout.addWidget(self.close_all_button)
        
        layout.addLayout(button_layout)
        
        # Info box
        info_box = QGroupBox("Info")
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "Videos open in tabs in the main view.\n"
            "Qt Multimedia syncs to JACK transport.\n"
            "Use Detach button for multi-monitor.\n"
            "Audio muted by default (JACK routing)."
        )
        info_label.setWordWrap(True)
        info_layout.addWidget(info_label)
        info_box.setLayout(info_layout)
        layout.addWidget(info_box)
    
    def _get_transcoded_path(self, source_path: Path) -> Optional[Path]:
        """
        Get transcoded video path for source file.
        Maps ~/Backups/Videos/... to ~/Videos/.../filename_video.mp4
        """
        try:
            backup_base = Path.home() / "Backups/Videos"
            videos_base = Path.home() / "Videos"
            
            if source_path.is_relative_to(backup_base):
                relative = source_path.relative_to(backup_base)
                transcoded = videos_base / relative.parent / f"{relative.stem}_video.mp4"
                return transcoded if transcoded.exists() else None
            
            return None
        except Exception as e:
            logger.error(f"Failed to get transcoded path: {e}")
            return None
    
    def _on_open_video(self):
        """Handle open video button click (Qt player for regular watching)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video File",
            str(Path.home()),
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.ogv *.flv *.wmv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            self._open_video_file(file_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open video:\n{str(e)}"
            )
    
    def _on_open_xjadeo(self):
        """Handle open in xjadeo button click (frame-accurate work)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video for xjadeo (frame-accurate)",
            str(Path.home() / "Backups/Videos"),
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.ogv *.flv *.wmv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        source_path = Path(file_path)
        transcoded_path = self._get_transcoded_path(source_path)
        
        if not transcoded_path:
            # Transcoded version doesn't exist
            reply = QMessageBox.question(
                self,
                "Transcode Required",
                f"This video needs to be transcoded for xjadeo frame-accurate work.\n\n"
                f"Original: {source_path.name}\n\n"
                f"Would you like to:\n"
                f"• Open Transcode panel to convert it?\n"
                f"• Or open original in Qt player instead (not frame-accurate)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Show transcode panel
                from skeleton_app.gui.main_window import MainWindow
                main_window = self.window()
                if hasattr(main_window, 'transcode_dock'):
                    main_window.transcode_dock.setVisible(True)
                    main_window.view_transcode_action.setChecked(True)
                QMessageBox.information(
                    self,
                    "Transcode Panel",
                    "Please transcode the video using the Transcode panel, then try opening in xjadeo again."
                )
            elif reply == QMessageBox.StandardButton.No:
                # Open original in Qt player
                self._open_video_file(str(source_path))
            
            return
        
        # Transcoded version exists - open it
        logger.info(f"Opening transcoded video for xjadeo: {transcoded_path}")
        try:
            self._open_video_file(str(transcoded_path))
        except Exception as e:
            logger.error(f"Failed to open transcoded video: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open transcoded video:\n{str(e)}"
            )
    
    def _open_video_file(self, file_path: str):
        """Common method to open a video file (extracted from _on_open_video)."""
        try:
            logger.info(f"Opening video file: {file_path}")
            
            # Create player with video file
            instance_id, player = self.video_manager.create_player(
                file_path=Path(file_path),
                sync_enabled=False  # Disable sync by default - enable via checkbox if needed
            )
            
            logger.info(f"Player created: {instance_id}")
            logger.info(f"Player state: {player.player.playbackState()}")
            logger.info(f"Media status: {player.player.mediaStatus()}")
            logger.info(f"Error: {player.player.error()}")
            
            # Check if file was loaded successfully
            if player.player.error() != QMediaPlayer.Error.NoError:
                error_msg = player.player.errorString()
                raise RuntimeError(f"Failed to load video: {error_msg}")
            
            # Create video player widget
            player_widget = VideoPlayerWidget(
                player, 
                mode="embedded",
                show_controls=True,
                enable_audio=False
            )
            player_widget.closed.connect(lambda: self._on_tab_close_requested(instance_id))
            
            # Store reference
            self.player_widgets[instance_id] = player_widget
            
            # Add as tab in main tab widget
            file_name = Path(file_path).name
            tab_index = self.tab_widget.addTab(player_widget, file_name)
            self.video_tabs[instance_id] = tab_index
            
            # Switch to new tab
            self.tab_widget.setCurrentIndex(tab_index)
            
            logger.info(f"Tab created at index {tab_index}, switching to it")
            
            # Start playback - use QTimer to ensure widget is shown first
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._start_playback(player, instance_id))
            
            logger.info(f"Opened video in tab: {file_path} (instance: {instance_id})")
            self.video_opened.emit(instance_id, file_path)
            self._refresh_list()
            
        except Exception as e:
            logger.error(f"Failed to open video: {e}", exc_info=True)
            raise
    
    def _on_screen_capture(self):
        """Open a screen capture tab."""
        try:
            self.capture_counter += 1
            instance_id = f"screen_capture_{self.capture_counter}"
            
            # Create screen capture widget
            capture_widget = ScreenCaptureWidget(instance_id)
            capture_widget.closed.connect(lambda: self._on_capture_close_requested(instance_id))
            
            # Store reference
            self.capture_widgets[instance_id] = capture_widget
            
            # Add as tab in main tab widget
            tab_name = f"Screen Capture {self.capture_counter}"
            tab_index = self.tab_widget.addTab(capture_widget, tab_name)
            self.video_tabs[instance_id] = tab_index
            
            # Switch to new tab
            self.tab_widget.setCurrentIndex(tab_index)
            
            logger.info(f"Opened screen capture in tab: {tab_name}")
            
        except Exception as e:
            logger.error(f"Failed to open screen capture: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open screen capture:\n{str(e)}"
            )
    
    def _on_capture_close_requested(self, instance_id: str):
        """Handle screen capture widget close."""
        logger.info(f"Closing screen capture: {instance_id}")
        
        # Cleanup widget
        widget = self.capture_widgets.pop(instance_id, None)
        if widget:
            widget.cleanup()
            widget.deleteLater()
        
        # Find and remove tab
        if instance_id in self.video_tabs:
            tab_index = self.video_tabs.pop(instance_id)
            self.tab_widget.removeTab(tab_index)
            
            # Update remaining tab indices
            for vid_id, idx in list(self.video_tabs.items()):
                if idx > tab_index:
                    self.video_tabs[vid_id] = idx - 1
        
        logger.info(f"Screen capture closed: {instance_id}")
    
    def _start_playback(self, player: QtVideoPlayer, instance_id: str):
        """Start video playback after widget is set up."""
        logger.info(f"Starting playback for {instance_id}")
        logger.info(f"Player state before play: {player.player.playbackState()}")
        logger.info(f"Media status before play: {player.player.mediaStatus()}")
        
        player.play()
        
        logger.info(f"Player state after play: {player.player.playbackState()}")
        logger.info(f"Position: {player.get_position_ms()}ms")
        logger.info(f"Duration: {player.get_duration_ms()}ms")
    
    def _on_tab_close_requested(self, instance_id: str):
        """Handle video player widget close."""
        logger.info(f"Closing video player: {instance_id}")
        
        # Cleanup widget first (stops timers)
        widget = self.player_widgets.pop(instance_id, None)
        if widget:
            widget.cleanup()
            widget.deleteLater()
        
        # Then remove player
        self.video_manager.remove_player(instance_id)
        
        # Find and remove tab
        if instance_id in self.video_tabs:
            tab_index = self.video_tabs.pop(instance_id)
            self.tab_widget.removeTab(tab_index)
            
            # Update remaining tab indices
            for vid_id, idx in list(self.video_tabs.items()):
                if idx > tab_index:
                    self.video_tabs[vid_id] = idx - 1
        
        self.video_closed.emit(instance_id)
        self._refresh_list()
        logger.info(f"Closed video player: {instance_id}")
    
    def _on_close_selected(self):
        """Close selected video from list."""
        selected_items = self.video_tree.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            instance_id = item.text(0).split(" - ")[0]
            self._on_tab_close_requested(instance_id)
    
    def _on_close_all(self):
        """Close all video instances."""
        try:
            for instance_id in list(self.player_widgets.keys()):
                self._on_tab_close_requested(instance_id)
            logger.info("Closed all video instances")
        except Exception as e:
            logger.error(f"Failed to close all instances: {e}")
    
    def _refresh_list(self):
        """Refresh the video list."""
        self.video_tree.clear()
        
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
                f"{instance_id} - {file_name}",
                state,
                sync_text
            ])
            
            # Color code sync state
            if stats.state.value == "synced":
                item.setForeground(2, Qt.green)
            elif stats.state.value in ["syncing", "drift"]:
                item.setForeground(2, Qt.yellow)
            else:
                item.setForeground(2, Qt.red)
            
            self.video_tree.addTopLevelItem(item)
        
        # Update button states
        has_instances = len(players) > 0
        self.close_button.setEnabled(has_instances)
        self.close_all_button.setEnabled(has_instances)
